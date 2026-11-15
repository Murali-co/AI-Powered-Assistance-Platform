import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.auth.models import DBManager
from app.auth.utils import verify_password
from app.db.session import engine


def test_auth_complete_lifecycle(client: TestClient):
    test_email = "e2e_verify_user@cognis.ai"
    test_password = "SecurePassword123!"
    test_name = "E2E Verified Candidate"

    # Clean up test user if existed from previous run
    existing = DBManager.get_user_by_email(test_email)
    if existing:
        DBManager.delete_user(existing["id"])

    # -------------------------------------------------------------
    # 1. New user registration
    # -------------------------------------------------------------
    reg_response = client.post("/auth/register", json={
        "email": test_email,
        "password": test_password,
        "full_name": test_name
    })
    assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
    reg_data = reg_response.json()
    assert "Registration successful" in reg_data["message"]

    # -------------------------------------------------------------
    # 2. Duplicate registration rejection
    # -------------------------------------------------------------
    dup_response = client.post("/auth/register", json={
        "email": test_email.upper(),  # Test case-insensitivity rejection
        "password": test_password,
        "full_name": test_name
    })
    assert dup_response.status_code == 400
    assert "Email already registered" in dup_response.json()["detail"]

    # Unverified login attempt succeeds with valid credentials
    unverified_res = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    assert unverified_res.status_code == 200
    assert "access_token" in unverified_res.json()

    # Retrieve user and verification token, then verify email
    user_record = DBManager.get_user_by_email(test_email)
    assert user_record is not None
    from app.services.email_service import EmailService
    token = EmailService._last_sent_verification_token
    assert token is not None
    verify_res = client.get(f"/auth/verify-email/{token}")
    assert verify_res.status_code == 200
    assert verify_res.json()["verified"] is True

    # -------------------------------------------------------------
    # 3. Login with correct credentials (after verification)
    # -------------------------------------------------------------
    login_response = client.post("/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    login_data = login_response.json()
    assert "access_token" in login_data
    assert login_data.get("requires_2fa") is False
    access_token = login_data["access_token"]
    assert len(access_token) > 20

    # Also test case-insensitive login (e.g. capitalized email)
    login_upper = client.post("/auth/login", json={
        "email": "E2E_VERIFY_USER@COGNIS.AI",
        "password": test_password
    })
    assert login_upper.status_code == 200, "Case-insensitive login failed"
    assert "access_token" in login_upper.json()

    # -------------------------------------------------------------
    # 4. Rejection of incorrect credentials
    # -------------------------------------------------------------
    wrong_pw_response = client.post("/auth/login", json={
        "email": test_email,
        "password": "WrongPassword999!"
    })
    assert wrong_pw_response.status_code == 401
    assert "Incorrect email or password" in wrong_pw_response.json()["detail"]

    # -------------------------------------------------------------
    # 5. Access to an authenticated endpoint
    # -------------------------------------------------------------
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    me_response = client.get("/auth/me", headers=auth_headers)
    assert me_response.status_code == 200
    user_info = me_response.json()
    assert user_info["email"] == test_email.lower()
    assert user_info["full_name"] == test_name
    assert user_info["two_factor_enabled"] is False
    user_id = user_info["id"]

    # -------------------------------------------------------------
    # 6. Rejection of unauthenticated requests
    # -------------------------------------------------------------
    unauth_client = TestClient(app)
    unauth_response = unauth_client.get("/auth/me")
    assert unauth_response.status_code == 401

    invalid_token_response = unauth_client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert invalid_token_response.status_code == 401

    # -------------------------------------------------------------
    # 7. Logout and token invalidation
    # -------------------------------------------------------------
    # Login again to capture fresh cookies
    fresh_login = client.post("/auth/login", json={"email": test_email, "password": test_password})
    csrf_token = fresh_login.cookies.get("csrf_token")
    if csrf_token:
        client.cookies.set("csrf_token", csrf_token)

    logout_response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token} if csrf_token else {})
    assert logout_response.status_code == 200

    # Refresh token should now fail because it was revoked by logout
    refresh_fail = client.post("/auth/refresh")
    assert refresh_fail.status_code == 401

    # -------------------------------------------------------------
    # 8. Two-factor authentication where enabled
    # -------------------------------------------------------------
    # Log back in to get active session
    relogin = client.post("/auth/login", json={"email": test_email, "password": test_password})
    active_token = relogin.json()["access_token"]
    csrf_token = relogin.cookies.get("csrf_token")
    if csrf_token:
        client.cookies.set("csrf_token", csrf_token)
    session_headers = {"Authorization": f"Bearer {active_token}"}
    if csrf_token:
        session_headers["X-CSRF-Token"] = csrf_token

    # 8a. Setup 2FA
    setup_res = client.post("/auth/2fa/setup", headers=session_headers)
    assert setup_res.status_code == 200
    totp_secret = setup_res.json()["secret"]
    assert len(totp_secret) >= 16

    # 8b. Confirm 2FA with TOTP code
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    confirm_res = client.post("/auth/2fa/confirm", json={
        "secret": totp_secret,
        "code": valid_code
    }, headers=session_headers)
    assert confirm_res.status_code == 200
    backup_codes = confirm_res.json()["backup_codes"]
    assert len(backup_codes) == 10

    # 8c. Login challenge requires 2FA
    challenge_res = client.post("/auth/login", json={"email": test_email, "password": test_password})
    assert challenge_res.status_code == 200
    assert challenge_res.json()["requires_2fa"] is True
    pending_token = challenge_res.json()["pending_token"]
    assert pending_token is not None

    # 8d. Reject invalid 2FA code
    bad_2fa = client.post("/auth/2fa/verify", json={"pending_token": pending_token, "code": "000000"})
    assert bad_2fa.status_code == 400

    # 8e. Verify with valid TOTP code
    valid_code_2 = totp.now()
    verify_res = client.post("/auth/2fa/verify", json={"pending_token": pending_token, "code": valid_code_2})
    assert verify_res.status_code == 200
    assert "access_token" in verify_res.json()

    # 8f. Verify using one backup code
    challenge_res_2 = client.post("/auth/login", json={"email": test_email, "password": test_password})
    pending_token_2 = challenge_res_2.json()["pending_token"]
    backup_code_to_use = backup_codes[0]
    backup_verify_res = client.post("/auth/2fa/verify", json={
        "pending_token": pending_token_2,
        "code": backup_code_to_use
    })
    assert backup_verify_res.status_code == 200
    assert "access_token" in backup_verify_res.json()

    # Reusing the same consumed backup code should fail
    challenge_res_3 = client.post("/auth/login", json={"email": test_email, "password": test_password})
    pending_token_3 = challenge_res_3.json()["pending_token"]
    reuse_res = client.post("/auth/2fa/verify", json={
        "pending_token": pending_token_3,
        "code": backup_code_to_use
    })
    assert reuse_res.status_code == 400

    # 8g. Disable 2FA
    authed_token_after_2fa = backup_verify_res.json()["access_token"]
    disable_csrf = backup_verify_res.cookies.get("csrf_token")
    if disable_csrf:
        client.cookies.set("csrf_token", disable_csrf)
    disable_headers = {"Authorization": f"Bearer {authed_token_after_2fa}"}
    if disable_csrf:
        disable_headers["X-CSRF-Token"] = disable_csrf
    disable_res = client.post("/auth/2fa/disable", json={
        "password": test_password
    }, headers=disable_headers)
    assert disable_res.status_code == 200

    # Verify subsequent login no longer prompts for 2FA
    login_after_disable = client.post("/auth/login", json={"email": test_email, "password": test_password})
    assert login_after_disable.status_code == 200
    assert login_after_disable.json()["requires_2fa"] is False
    assert "access_token" in login_after_disable.json()

    # -------------------------------------------------------------
    # 9. Persistence of the user in Neon
    # -------------------------------------------------------------
    with engine.connect() as conn:
        res = conn.execute(text("SELECT id, email, full_name, hashed_password, is_admin FROM users WHERE id = :uid"), {"uid": user_id})
        persisted_row = res.fetchone()
        assert persisted_row is not None, "User was not persisted in database"
        assert persisted_row[1] == test_email.lower()
        assert persisted_row[2] == test_name
        assert verify_password(test_password, persisted_row[3]) is True
        assert bool(persisted_row[4]) is False

    # -------------------------------------------------------------
    # 10. Clean up test user
    # -------------------------------------------------------------
    DBManager.delete_user(user_id)
    assert DBManager.get_user_by_email(test_email) is None
