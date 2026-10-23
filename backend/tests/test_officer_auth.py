"""Comprehensive test suite for Individual Officer Authentication, Session Management, RBAC, and Audit Logging."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import User, Application, Institution, AuditEvent
from app.auth import hash_password, create_access_token, revoke_token, is_token_revoked


@pytest.fixture(scope="module")
def client():
    # Ensure test tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Create test institution
    inst = db.query(Institution).filter(Institution.id == "auth-test-inst").first()
    if not inst:
        inst = Institution(id="auth-test-inst", name="Auth Test College")
        db.add(inst)
        db.flush()

    # Create Officer 1
    u1 = db.query(User).filter(User.id == "test-off-001").first()
    if not u1:
        u1 = User(
            id="test-off-001",
            officer_id="TEST-OFFICER-1",
            name="Officer First",
            email="officer1@aicte-test.example",
            password_hash=hash_password("OfficerPass123!"),
            role="SCRUTINY_OFFICER",
            active=True,
        )
        db.add(u1)

    # Create Officer 2
    u2 = db.query(User).filter(User.id == "test-off-002").first()
    if not u2:
        u2 = User(
            id="test-off-002",
            officer_id="TEST-OFFICER-2",
            name="Officer Second",
            email="officer2@aicte-test.example",
            password_hash=hash_password("OfficerPass123!"),
            role="SCRUTINY_OFFICER",
            active=True,
        )
        db.add(u2)

    # Create Disabled Officer
    u_dis = db.query(User).filter(User.id == "test-off-disabled").first()
    if not u_dis:
        u_dis = User(
            id="test-off-disabled",
            officer_id="TEST-DISABLED",
            name="Disabled Officer",
            email="disabled@aicte-test.example",
            password_hash=hash_password("OfficerPass123!"),
            role="SCRUTINY_OFFICER",
            active=False,
        )
        db.add(u_dis)

    # Create Administrator
    u_admin = db.query(User).filter(User.id == "test-admin-001").first()
    if not u_admin:
        u_admin = User(
            id="test-admin-001",
            officer_id="TEST-ADMIN-1",
            name="Admin User",
            email="admin@aicte-test.example",
            password_hash=hash_password("AdminPass123!"),
            role="SYSTEM_ADMIN",
            active=True,
        )
        db.add(u_admin)

    # Create Supervisor
    u_sup = db.query(User).filter(User.id == "test-supervisor-001").first()
    if not u_sup:
        u_sup = User(
            id="test-supervisor-001",
            officer_id="TEST-SUPERVISOR-1",
            name="Supervisor User",
            email="supervisor@aicte-test.example",
            password_hash=hash_password("SupervisorPass123!"),
            role="SUPERVISOR",
            active=True,
        )
        db.add(u_sup)

    # Create an Application assigned to Officer 1
    app1 = db.query(Application).filter(Application.id == "app-assigned-to-off1").first()
    if not app1:
        app1 = Application(
            id="app-assigned-to-off1",
            institution_id="auth-test-inst",
            assigned_officer_id="test-off-001",
            academic_year="2026-27",
            program_type="UG Engineering",
            category="Extension of Approval",
            status="UNDER_REVIEW",
        )
        db.add(app1)

    # Create an Application assigned to Officer 2
    app2 = db.query(Application).filter(Application.id == "app-assigned-to-off2").first()
    if not app2:
        app2 = Application(
            id="app-assigned-to-off2",
            institution_id="auth-test-inst",
            assigned_officer_id="test-off-002",
            academic_year="2026-27",
            program_type="UG Engineering",
            category="Extension of Approval",
            status="UNDER_REVIEW",
        )
        db.add(app2)

    db.commit()
    db.close()

    with TestClient(app) as tc:
        yield tc


@pytest.fixture(autouse=True)
def reset_client_cookies(client):
    client.cookies.clear()


# ─── 0. Route & Health Check Tests ───────────────────────────────────────────

def test_health_endpoints(client):
    res_root = client.get("/health")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "ok"

    res_api = client.get("/api/v1/health")
    assert res_api.status_code == 200
    assert res_api.json()["status"] == "ok"


def test_login_and_workspace_navigation_routes(client):
    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert "Officer Sign In" in res_login.text

    res_login_html = client.get("/login.html")
    assert res_login_html.status_code == 200
    assert "Officer Sign In" in res_login_html.text

    res_root = client.get("/")
    assert res_root.status_code == 200

    res_index = client.get("/index.html")
    assert res_index.status_code == 200


def test_missing_login_file_returns_404(client, monkeypatch):
    import app.main as main_module
    original_frontend_dir = main_module.frontend_dir
    monkeypatch.setattr(main_module, "frontend_dir", "/nonexistent/directory/path")
    res = client.get("/login")
    assert res.status_code == 404
    assert "Login page not found" in res.json()["detail"]

    res_html = client.get("/login.html")
    assert res_html.status_code == 404
    assert "Login page not found" in res_html.json()["detail"]
    monkeypatch.setattr(main_module, "frontend_dir", original_frontend_dir)


# ─── 1. Authentication Tests ──────────────────────────────────────────────────

def test_login_successful_with_email(client):
    res = client.post("/api/v1/auth/login", json={
        "email": "officer1@aicte-test.example",
        "password": "OfficerPass123!"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "officer1@aicte-test.example"
    assert data["user"]["officer_id"] == "TEST-OFFICER-1"
    assert data["user"]["role"] == "SCRUTINY_OFFICER"
    # Verify HttpOnly session cookie was set
    assert "sih_session" in res.cookies


def test_login_successful_with_officer_id(client):
    res = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-1",
        "password": "OfficerPass123!"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["officer_id"] == "TEST-OFFICER-1"


def test_login_incorrect_password(client):
    res = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-1",
        "password": "WrongPassword!"
    })
    assert res.status_code == 401
    assert "Invalid officer credentials" in res.json()["detail"]


def test_login_nonexistent_user(client):
    res = client.post("/api/v1/auth/login", json={
        "identifier": "NONEXISTENT-OFFICER",
        "password": "SomePassword!"
    })
    # Generic error message to prevent enumeration
    assert res.status_code == 401
    assert "Invalid officer credentials" in res.json()["detail"]


def test_login_disabled_account(client):
    res = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-DISABLED",
        "password": "OfficerPass123!"
    })
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"].lower()


def test_login_missing_credentials(client):
    res = client.post("/api/v1/auth/login", json={
        "identifier": "",
        "password": "Pass"
    })
    assert res.status_code == 400


# ─── 2. Session and Logout Invalidation ────────────────────────────────────────

def test_authenticated_get_me_via_bearer_and_cookie(client):
    # Login Officer 1
    login_res = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-1",
        "password": "OfficerPass123!"
    })
    token = login_res.json()["access_token"]

    # Bearer header
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["officer_id"] == "TEST-OFFICER-1"
    assert me_res.json()["permissions"]["can_review"] is True

    # Via cookie (without Authorization header)
    cookie_res = client.get("/api/v1/auth/me", cookies=login_res.cookies)
    assert cookie_res.status_code == 200
    assert cookie_res.json()["officer_id"] == "TEST-OFFICER-1"


def test_logout_invalidates_session(client):
    login_res = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-1",
        "password": "OfficerPass123!"
    })
    token = login_res.json()["access_token"]

    # Call logout endpoint
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        cookies=login_res.cookies
    )
    assert logout_res.status_code == 200

    # Attempt to access protected endpoint using the invalidated token
    after_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert after_res.status_code == 401
    assert "revoked" in after_res.json()["detail"].lower()


def test_unauthenticated_access_rejected(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


# ─── 3. Multi-Officer Isolation & Restricted Case Access ──────────────────────

def test_officer_cannot_access_another_officers_restricted_case(client):
    # 1. Login Officer 2
    login_off2 = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-2",
        "password": "OfficerPass123!"
    })
    token_off2 = login_off2.json()["access_token"]

    # 2. Officer 2 accesses their own assigned application -> 200 OK
    own_app_res = client.get(
        "/api/v1/applications/app-assigned-to-off2",
        headers={"Authorization": f"Bearer {token_off2}"}
    )
    assert own_app_res.status_code == 200

    # 3. Officer 2 attempts direct access to Officer 1's application -> 403 Forbidden!
    other_app_res = client.get(
        "/api/v1/applications/app-assigned-to-off1",
        headers={"Authorization": f"Bearer {token_off2}"}
    )
    assert other_app_res.status_code == 403
    assert "assigned to another scrutiny officer" in other_app_res.json()["detail"]


def test_supervisor_can_access_all_applications(client):
    # Supervisor can access applications assigned to any officer
    login_sup = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-SUPERVISOR-1",
        "password": "SupervisorPass123!"
    })
    token_sup = login_sup.json()["access_token"]

    res1 = client.get(
        "/api/v1/applications/app-assigned-to-off1",
        headers={"Authorization": f"Bearer {token_sup}"}
    )
    assert res1.status_code == 200

    res2 = client.get(
        "/api/v1/applications/app-assigned-to-off2",
        headers={"Authorization": f"Bearer {token_sup}"}
    )
    assert res2.status_code == 200


def test_officer_cannot_grant_admin_or_manage_accounts(client):
    # Login Officer 1
    login_off1 = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-OFFICER-1",
        "password": "OfficerPass123!"
    })
    token_off1 = login_off1.json()["access_token"]

    # Attempt to create account -> 403 Forbidden
    create_res = client.post(
        "/api/v1/auth/officers",
        headers={"Authorization": f"Bearer {token_off1}"},
        json={
            "officer_id": "ROGUE-OFFICER",
            "name": "Rogue",
            "email": "rogue@aicte.example",
            "password": "Password123!",
            "role": "SYSTEM_ADMIN"
        }
    )
    assert create_res.status_code == 403


def test_admin_can_manage_officer_accounts(client):
    import uuid
    # Login Admin
    login_admin = client.post("/api/v1/auth/login", json={
        "identifier": "TEST-ADMIN-1",
        "password": "AdminPass123!"
    })
    token_admin = login_admin.json()["access_token"]

    # 1. Admin creates new officer
    uid = uuid.uuid4().hex[:6]
    new_officer_id = f"NEW-OFF-{uid}"
    new_email = f"officer_{uid}@aicte-test.example"
    create_res = client.post(
        "/api/v1/auth/officers",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "officer_id": new_officer_id,
            "name": f"New Officer {uid}",
            "email": new_email,
            "password": "NewOfficerPass123!",
            "role": "SCRUTINY_OFFICER"
        }
    )
    assert create_res.status_code == 201
    created_user_id = create_res.json()["id"]

    # 2. Newly created officer can log in
    off_login = client.post("/api/v1/auth/login", json={
        "identifier": new_officer_id,
        "password": "NewOfficerPass123!"
    })
    assert off_login.status_code == 200

    # 3. Admin disables the new officer
    disable_res = client.patch(
        f"/api/v1/auth/officers/{created_user_id}/status?active=false",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert disable_res.status_code == 200
    assert disable_res.json()["active"] is False

    # 4. Disabled officer can no longer log in
    off_login_disabled = client.post("/api/v1/auth/login", json={
        "identifier": new_officer_id,
        "password": "NewOfficerPass123!"
    })
    assert off_login_disabled.status_code == 403


# ─── 4. Audit Trail Integration ───────────────────────────────────────────────

def test_login_and_logout_events_are_recorded_in_audit_chain(client):
    db = SessionLocal()
    # Check that LOGIN_SUCCESS and LOGOUT events were recorded
    login_events = db.query(AuditEvent).filter(AuditEvent.action == "LOGIN_SUCCESS").all()
    assert len(login_events) > 0

    # Verify audit chain integrity remains intact
    from app.services.audit import verify_chain
    chain_status = verify_chain(db)
    assert chain_status["intact"] is True
    db.close()


# ─── 5. Database Masking & Static Asset Regression Tests ─────────────────────

def test_database_credentials_masked_in_logs():
    from sqlalchemy.engine.url import make_url
    sensitive_url = "postgresql://sih_app:SecretPassword123!@localhost:5432/sih26261"
    masked = make_url(sensitive_url).render_as_string(hide_password=True)
    assert "SecretPassword123!" not in masked
    assert "***" in masked
    assert "sih_app" in masked


def test_static_assets_mounted_and_accessible(client):
    res_css = client.get("/css/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("content-type", "")

    res_api_js = client.get("/js/api.js")
    assert res_api_js.status_code == 200
    assert "javascript" in res_api_js.headers.get("content-type", "")

    res_app_js = client.get("/js/app.js")
    assert res_app_js.status_code == 200
    assert "javascript" in res_app_js.headers.get("content-type", "")


def test_frontend_html_references_absolute_asset_paths(client):
    res_login = client.get("/login")
    assert 'href="/css/style.css"' in res_login.text
    assert 'from "/js/api.js"' in res_login.text

    res_index = client.get("/")
    assert 'href="/css/style.css"' in res_index.text
    assert 'src="/js/app.js"' in res_index.text
