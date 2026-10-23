"""Live End-to-End Integration Verification Script against running application."""
import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"


def test_live_routes_and_assets():
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        # 1. Landing page
        r_root = client.get("/")
        assert r_root.status_code == 200
        assert "AICTE" in r_root.text

        # 2. Login routes
        r_login = client.get("/login")
        assert r_login.status_code == 200
        assert "Officer Sign In" in r_login.text

        r_login_html = client.get("/login.html")
        assert r_login_html.status_code == 200
        assert "Officer Sign In" in r_login_html.text

        # 3. Static assets
        r_css = client.get("/css/style.css")
        assert r_css.status_code == 200
        assert "text/css" in r_css.headers.get("content-type", "")

        r_js = client.get("/js/api.js")
        assert r_js.status_code == 200
        assert "javascript" in r_js.headers.get("content-type", "")

        # 4. Missing route produces 404
        r_404 = client.get("/nonexistent-route-for-testing")
        assert r_404.status_code == 404
        assert r_404.json().get("detail") == "Not Found"


def test_live_authentication_lifecycle():
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        # Unauthenticated access rejected
        r_unauth = client.get("/api/v1/auth/me")
        assert r_unauth.status_code == 401

        # Invalid credentials rejected
        r_bad = client.post("/api/v1/auth/login", json={"identifier": "INVALID_OFFICER", "password": "WrongPassword!"})
        assert r_bad.status_code == 401
        assert "Invalid officer credentials" in r_bad.json().get("detail", "")

        # Valid login
        r_login = client.post("/api/v1/auth/login", json={"identifier": "OFFICER-001", "password": "demo1234"})
        assert r_login.status_code == 200
        data = r_login.json()
        token = data["access_token"]
        assert data["user"]["officer_id"] == "OFFICER-001"
        assert "sih_session" in client.cookies

        # Profile retrieval with cookie
        r_me = client.get("/api/v1/auth/me")
        assert r_me.status_code == 200
        assert r_me.json()["officer_id"] == "OFFICER-001"

        # Applications list accessible
        r_apps = client.get("/api/v1/applications")
        assert r_apps.status_code == 200
        assert isinstance(r_apps.json(), list)

        # Logout
        r_logout = client.post("/api/v1/auth/logout")
        assert r_logout.status_code == 200

        # Session cookie invalidated
        r_me_after = client.get("/api/v1/auth/me")
        assert r_me_after.status_code == 401

        # Bearer token explicitly revoked
        r_token_after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r_token_after.status_code == 401
        assert "revoked" in r_token_after.json().get("detail", "").lower()


def test_live_health_endpoints():
    with httpx.Client(base_url=BASE_URL) as client:
        for path in ("/health", "/api/v1/health"):
            res = client.get(path)
            assert res.status_code == 200
            assert res.json().get("status") == "ok"
