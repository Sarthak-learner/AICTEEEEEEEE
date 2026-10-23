from datetime import datetime, timezone, timedelta
from typing import Optional, Set
import time
import uuid
from collections import defaultdict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole

settings = get_settings()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# Server-side token / session revocation blocklist (session invalidation on logout)
# Stores token jti or raw token strings with expiration timestamp
_revoked_tokens: Set[str] = set()

# Login rate limiting: IP / Identifier -> list of failed attempt timestamps
_failed_attempts = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
MAX_FAILED_ATTEMPTS = 5


def check_rate_limit(identifier: str) -> bool:
    """Check if identifier or IP has exceeded failed login attempts."""
    now = time.time()
    attempts = _failed_attempts[identifier]
    # Filter attempts within window
    valid_attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    _failed_attempts[identifier] = valid_attempts
    return len(valid_attempts) < MAX_FAILED_ATTEMPTS


def record_failed_attempt(identifier: str):
    """Record a failed login attempt for rate limiting."""
    _failed_attempts[identifier].append(time.time())


def clear_failed_attempts(identifier: str):
    """Clear failed attempts upon successful login."""
    if identifier in _failed_attempts:
        del _failed_attempts[identifier]


def revoke_token(token: str):
    """Add a token and its jti to the server-side revocation set."""
    if token:
        _revoked_tokens.add(token)
        try:
            unverified = jwt.get_unverified_claims(token)
            if "jti" in unverified:
                _revoked_tokens.add(unverified["jti"])
        except Exception:
            pass


def is_token_revoked(token: str) -> bool:
    """Check if a token or jti has been explicitly invalidated / logged out."""
    return token in _revoked_tokens


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    if "jti" not in to_encode:
        to_encode["jti"] = uuid.uuid4().hex
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    if "jti" not in to_encode:
        to_encode["jti"] = uuid.uuid4().hex
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_token_revoked(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    # 1. Try Authorization header Bearer token
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    # 2. Try HttpOnly session cookie
    elif "sih_session" in request.cookies:
        token = request.cookies.get("sih_session")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account does not exist")
    if not user.active:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact administrator.")

    return user


def require_roles(*roles: str):
    """Dependency factory that enforces role-based access."""
    # Normalize aliases: SUPERVISOR maps to SENIOR_REVIEWER or SUPERVISOR
    allowed_roles = set(roles)
    if "SUPERVISOR" in allowed_roles:
        allowed_roles.add("SENIOR_REVIEWER")
    if "SENIOR_REVIEWER" in allowed_roles:
        allowed_roles.add("SUPERVISOR")
    if "ADMINISTRATOR" in allowed_roles:
        allowed_roles.add("SYSTEM_ADMIN")
    if "SYSTEM_ADMIN" in allowed_roles:
        allowed_roles.add("ADMINISTRATOR")

    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role}' is not authorized. Required: {list(roles)}"
            )
        return user
    return _check
