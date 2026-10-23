"""Auth API endpoints: login, logout, refresh, officer management, current officer profile."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field

from app.database import get_db
from app.models import User, Institution
from app.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, require_roles, revoke_token,
    check_rate_limit, record_failed_attempt, clear_failed_attempts,
)
from app.services.audit import record_event

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    # Accepts either email or officer_id
    identifier: Optional[str] = None
    email: Optional[str] = None
    password: str = Field(..., min_length=1)


class OfficerCreateRequest(BaseModel):
    officer_id: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=8)
    role: str = "SCRUTINY_OFFICER"  # SCRUTINY_OFFICER | SUPERVISOR | SYSTEM_ADMIN
    institution_id: Optional[str] = None


class OfficerUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    login_id = (req.identifier or req.email or "").strip()

    if not login_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Officer ID or official email is required."
        )

    # 1. Rate limiting check
    rate_key = f"{client_ip}:{login_id}"
    if not check_rate_limit(rate_key):
        record_event(
            db, "LOGIN_RATE_LIMITED", actor_id=None, object_type="user", object_id=login_id,
            payload={"ip": client_ip, "reason": "Too many failed attempts"},
            ip_address=client_ip
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes before trying again."
        )

    # 2. Look up user by email OR officer_id
    user = db.query(User).filter(
        or_(User.email == login_id, User.officer_id == login_id)
    ).first()

    # Generic invalid credential response to avoid account enumeration
    if not user or not verify_password(req.password, user.password_hash):
        record_failed_attempt(rate_key)
        record_event(
            db, "LOGIN_FAILED", actor_id=user.id if user else None, object_type="user",
            object_id=login_id, payload={"reason": "Invalid credentials", "ip": client_ip},
            ip_address=client_ip
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid officer credentials. Check Officer ID / Email and password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Check account status
    if not user.active:
        record_event(
            db, "LOGIN_REJECTED_DISABLED", actor_id=user.id, object_type="user",
            object_id=user.id, payload={"reason": "Account disabled", "ip": client_ip},
            ip_address=client_ip
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This officer account has been disabled. Please contact your system administrator."
        )

    # Clear rate limit counter on success
    clear_failed_attempts(rate_key)

    # Invalidate previous session tokens if this is an explicit session rotation / account switch
    if request.headers.get("X-Switch-Account") == "true":
        old_cookie_token = request.cookies.get("sih_session")
        if old_cookie_token:
            revoke_token(old_cookie_token)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            revoke_token(auth_header.split(" ")[1])

    # Create tokens
    token_payload = {
        "sub": user.id,
        "officer_id": user.officer_id,
        "role": user.role,
        "email": user.email,
        "name": user.name,
    }
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token({"sub": user.id})

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key="sih_session",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in HTTPS production; False allows localhost HTTP
        max_age=3600,
        path="/",
    )

    record_event(
        db, "LOGIN_SUCCESS", actor_id=user.id, object_type="user", object_id=user.id,
        payload={"officer_id": user.officer_id, "role": user.role, "ip": client_ip},
        ip_address=client_ip
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "officer_id": user.officer_id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "institution_id": user.institution_id,
            "active": user.active,
        },
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sign out: invalidate session on server-side and clear HttpOnly cookie."""
    client_ip = request.client.host if request.client else "unknown"

    # Revoke bearer token if present
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        revoke_token(auth_header.split(" ")[1])

    # Revoke cookie token if present
    cookie_token = request.cookies.get("sih_session")
    if cookie_token:
        revoke_token(cookie_token)

    # Clear cookie
    response.delete_cookie(key="sih_session", path="/")

    record_event(
        db, "LOGOUT", actor_id=current_user.id, object_type="user",
        object_id=current_user.id, payload={"officer_id": current_user.officer_id},
        ip_address=client_ip
    )
    db.commit()

    return {"message": "Successfully logged out. Session invalidated.", "success": True}


@router.post("/refresh")
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    access_token = create_access_token({
        "sub": user.id,
        "officer_id": user.officer_id,
        "role": user.role,
        "email": user.email,
        "name": user.name,
    })
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    """Retrieve profile and permissions for currently authenticated officer."""
    # Compute permission flags based on role
    permissions = {
        "can_review": current_user.role in ("SCRUTINY_OFFICER", "SENIOR_REVIEWER", "SUPERVISOR", "SYSTEM_ADMIN"),
        "can_supervise": current_user.role in ("SENIOR_REVIEWER", "SUPERVISOR", "SYSTEM_ADMIN"),
        "can_manage_accounts": current_user.role in ("SYSTEM_ADMIN", "ADMINISTRATOR"),
        "can_view_audit": current_user.role in ("AUDITOR", "SYSTEM_ADMIN", "SENIOR_REVIEWER", "SUPERVISOR"),
        "can_edit_rulebook": current_user.role in ("CURATOR", "SYSTEM_ADMIN"),
    }
    return {
        "id": current_user.id,
        "officer_id": current_user.officer_id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "institution_id": current_user.institution_id,
        "active": current_user.active,
        "permissions": permissions,
    }


# ─── Administrator Account Management ──────────────────────────────────────────

@router.get("/officers", response_model=List[dict])
def list_officers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SYSTEM_ADMIN", "ADMINISTRATOR", "SUPERVISOR", "SENIOR_REVIEWER")),
):
    """List officer accounts (admin / supervisor only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "officer_id": u.officer_id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "active": u.active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/officers", status_code=201)
def create_officer_account(
    req: OfficerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SYSTEM_ADMIN", "ADMINISTRATOR")),
):
    """Create a new officer account (Administrator workflow)."""
    # Check email uniqueness
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    # Check officer_id uniqueness
    if db.query(User).filter(User.officer_id == req.officer_id).first():
        raise HTTPException(status_code=400, detail="Officer ID already registered.")

    user = User(
        officer_id=req.officer_id,
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=req.role,
        institution_id=req.institution_id,
        active=True,
    )
    db.add(user)
    db.flush()

    record_event(
        db, "OFFICER_ACCOUNT_CREATED", actor_id=current_user.id, object_type="user",
        object_id=user.id, payload={"officer_id": user.officer_id, "role": user.role, "email": user.email}
    )
    db.commit()

    return {
        "id": user.id,
        "officer_id": user.officer_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "message": f"Officer account '{user.officer_id}' successfully created.",
    }


@router.patch("/officers/{user_id}/status")
def set_officer_status(
    user_id: str,
    active: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SYSTEM_ADMIN", "ADMINISTRATOR")),
):
    """Enable or disable an officer account (Administrator workflow)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Officer account not found.")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Administrators cannot disable their own account.")

    old_status = user.active
    user.active = active
    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    action = "OFFICER_ACCOUNT_ENABLED" if active else "OFFICER_ACCOUNT_DISABLED"
    record_event(
        db, action, actor_id=current_user.id, object_type="user",
        object_id=user.id, payload={"officer_id": user.officer_id, "from": old_status, "to": active}
    )
    db.commit()

    return {
        "id": user.id,
        "officer_id": user.officer_id,
        "active": user.active,
        "message": f"Account status updated to {'enabled' if active else 'disabled'}.",
    }


# Backwards compatibility register endpoint (for existing scripts/tests)
@router.post("/register", status_code=201)
def register(req: OfficerCreateRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        officer_id=req.officer_id,
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=req.role,
        institution_id=req.institution_id,
        active=True,
    )
    db.add(user)
    db.flush()

    record_event(
        db, "USER_REGISTERED", actor_id=user.id, object_type="user", object_id=user.id,
        payload={"role": req.role, "officer_id": req.officer_id}
    )
    db.commit()
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
