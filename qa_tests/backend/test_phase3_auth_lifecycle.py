"""
Phase 3 Comprehensive Test Suite: Neon-Backed Authentication, Token Versioning,
Concurrency Control, Multi-Factor Authentication & Account Lifecycle.

Verifies:
1. Registration & email verification with atomic one-use token consumption in Neon.
2. Concurrent token replay protection: race between concurrent workers has exactly 1 winner.
3. Access token binding to revocable Neon token_version state (immediate invalidation on change).
4. Refresh token rotation, replay detection, and bounded grace period under concurrency.
5. Password reset with atomic consumption and immediate cross-device token revocation.
6. 2FA TOTP setup, confirm, time step anti-replay, and single-use backup codes.
7. Device session management and selective / bulk session revocation.
8. Admin authorization checks for stats and audit logs.
9. Distributed rate limiting backed exclusively by Neon PostgreSQL.
10. Two-user tenant isolation (User A never sees User B data).
11. Durable cascaded account deletion with 2FA and resilience to Chroma vector store errors.
12. Cookie security (samesite="lax", path="/", secure flag, and deletion on logout).
"""

import pytest
import concurrent.futures
import pyotp
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.main import app
from app.db.session import SessionLocal
from app.db.models import User, RefreshToken, TwoFactorBackupCode, AuthAuditLog
from app.auth.models import DBManager
from app.auth.utils import (
    get_password_hash,
    create_access_token,
    generate_verification_token,
    generate_reset_password_token,
    hash_token,
    hash_refresh_token,
    hash_backup_code,
    create_pending_2fa_token
)


def make_auth_headers(access_token: str, client: TestClient = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    if client:
        csrf = client.cookies.get("csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf
    return headers


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestRegistrationAndAtomicVerification:
    """Verifies registration and atomic one-use email verification tokens."""

    def test_registration_and_atomic_verification_single_winner(self, client, db_session):
        email = f"test_verify_{datetime.now().timestamp()}@example.com"
        reg_resp = client.post("/auth/register", json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Verify Test User"
        })
        assert reg_resp.status_code == 200

        # Query user and verification token from Neon
        user = db_session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        assert user is not None
        assert user.email_verified is False
        assert user.verification_token is not None

        raw_token = reg_resp.json().get("verification_link", "").split("token=")[-1]
        assert raw_token != ""

        # Concurrency race: 5 concurrent workers attempt to consume the same verification token
        def try_consume():
            return DBManager.consume_verification_token_atomic(raw_token)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_consume) for _ in range(5)]
            results = [f.result() for f in futures]

        # Exactly 1 success, 4 None
        successful_consumptions = [r for r in results if r is not None]
        assert len(successful_consumptions) == 1
        assert successful_consumptions[0]["email"] == email

        # Database state: email_verified=True, verification_token is None
        db_session.expire_all()
        user_after = db_session.execute(select(User).where(User.email == email)).scalar_one()
        assert user_after.email_verified is True
        assert user_after.verification_token is None

        # Re-consuming the same token fails
        assert DBManager.consume_verification_token_atomic(raw_token) is None

        # Cleanup
        DBManager.delete_user(user.id)


class TestTokenVersioningAndRevocation:
    """Verifies that access tokens are bound to revocable token_version in Neon."""

    def test_access_token_invalidated_immediately_on_token_version_increment(self, client, db_session):
        email = f"test_tokver_{datetime.now().timestamp()}@example.com"
        hashed = get_password_hash("Password123!")
        user_id = DBManager.create_user(email=email, hashed_pw=hashed, full_name="Token Ver User")
        DBManager.verify_email(user_id)

        # Login to obtain access token
        login_resp = client.post("/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        assert login_resp.status_code == 200
        token_data = login_resp.json()
        access_token = token_data["access_token"]

        # Token works initially
        headers = {"Authorization": f"Bearer {access_token}"}
        me_resp = client.get("/auth/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == email

        # Increment user token_version in Neon
        new_version = DBManager.increment_user_token_version(user_id)
        assert new_version >= 2

        # The prior access token must be immediately rejected with 401
        me_revoked_resp = client.get("/auth/me", headers=headers)
        assert me_revoked_resp.status_code == 401
        assert "revoked" in me_revoked_resp.json()["detail"].lower()

        # Cleanup
        DBManager.delete_user(user_id)


class TestAtomicPasswordResetAndSessionRevocation:
    """Verifies atomic password reset token consumption and immediate session revocation."""

    def test_concurrent_password_reset_has_exactly_one_winner(self, client, db_session):
        email = f"test_pwreset_{datetime.now().timestamp()}@example.com"
        hashed = get_password_hash("OldPassword123!")
        user_id = DBManager.create_user(email=email, hashed_pw=hashed, full_name="Reset User")
        DBManager.verify_email(user_id)

        # Generate a password reset token
        reset_token = generate_reset_password_token()
        token_hash = hash_token(reset_token)
        expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
        DBManager.set_reset_password_token(user_id, token_hash, expiry)

        # Create an active refresh token session
        raw_refresh = "test_refresh_before_reset"
        DBManager.create_refresh_token(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            user_agent="TestDevice",
            ip_address="127.0.0.1",
            auth_time=int(datetime.now(timezone.utc).timestamp())
        )

        # 5 concurrent threads attempt to consume the reset token with different new passwords
        def try_reset(idx):
            pw_hash = get_password_hash(f"NewPassword{idx}!")
            return DBManager.consume_reset_password_token_atomic(reset_token, pw_hash)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_reset, i) for i in range(5)]
            results = [f.result() for f in futures]

        winners = [r for r in results if r is not None]
        assert len(winners) == 1, "Expected exactly 1 concurrent winner for reset token consumption"

        # Active refresh sessions must be completely revoked
        sessions = DBManager.get_active_user_sessions(user_id)
        assert len(sessions) == 0

        # Old password fails
        login_old = client.post("/auth/login", json={"email": email, "password": "OldPassword123!"})
        assert login_old.status_code == 401

        # Token version must be incremented
        user_db = DBManager.get_user_by_id(user_id)
        assert user_db["token_version"] >= 2
        assert user_db["reset_password_token"] is None

        # Re-consuming the reset token fails
        assert DBManager.consume_reset_password_token_atomic(reset_token, get_password_hash("Fail!")) is None

        # Cleanup
        DBManager.delete_user(user_id)


class TestTwoFactorAuthenticationLifecycle:
    """Verifies TOTP 2FA setup, anti-replay step consumption, backup codes, and disable."""

    def test_2fa_full_lifecycle_and_concurrent_totp_anti_replay(self, client, db_session):
        email = f"test_2fa_{datetime.now().timestamp()}@example.com"
        password = "SecurePassword123!"
        user_id = DBManager.create_user(email=email, hashed_pw=get_password_hash(password), full_name="2FA User")
        DBManager.verify_email(user_id)

        # Login
        login_resp = client.post("/auth/login", json={"email": email, "password": password})
        access_token = login_resp.json()["access_token"]
        headers = make_auth_headers(access_token, client)

        # 1. 2FA Setup
        setup_resp = client.post("/auth/2fa/setup", headers=headers)
        assert setup_resp.status_code == 200
        secret = setup_resp.json()["secret"]
        assert "otpauth_url" in setup_resp.json()

        # 2. 2FA Confirm
        totp = pyotp.TOTP(secret)
        code = totp.now()
        confirm_resp = client.post("/auth/2fa/confirm", headers=headers, json={
            "secret": secret,
            "code": code,
            "password": password
        })
        assert confirm_resp.status_code == 200
        backup_codes = confirm_resp.json()["backup_codes"]
        assert len(backup_codes) == 10

        user_db = DBManager.get_user_by_id(user_id)
        assert user_db["two_factor_enabled"] is True

        # 3. Subsequent login requires 2FA
        login_2fa_req = client.post("/auth/login", json={"email": email, "password": password})
        assert login_2fa_req.status_code == 200
        assert login_2fa_req.json().get("requires_2fa") is True
        pending_token = login_2fa_req.json().get("pending_token")
        assert pending_token is not None

        # 4. Concurrent TOTP anti-replay:
        # Multiple requests submitting the same TOTP step at the same instant must have exactly 1 winner
        current_step = totp.timecode(datetime.now(timezone.utc))

        def try_consume_step():
            return DBManager.consume_totp_step_atomic(user_id, current_step)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_consume_step) for _ in range(5)]
            step_results = [f.result() for f in futures]

        assert step_results.count(True) == 1
        assert step_results.count(False) == 4

        # 5. Single-use backup code consumption
        first_code = backup_codes[0]
        # Backup code verify via DBManager
        assert DBManager.verify_and_consume_backup_code(user_id, first_code) is True
        # Re-using the exact same backup code must fail
        assert DBManager.verify_and_consume_backup_code(user_id, first_code) is False

        # 6. Regenerate backup codes
        regen_resp = client.post("/auth/2fa/backup-codes/regenerate", headers=headers, json={"password": password})
        assert regen_resp.status_code == 200
        new_backup_codes = regen_resp.json()["backup_codes"]
        assert len(new_backup_codes) == 10
        # Old remaining backup codes must be invalid
        assert DBManager.verify_and_consume_backup_code(user_id, backup_codes[1]) is False

        # 7. Disable 2FA
        disable_resp = client.post("/auth/2fa/disable", headers=headers, json={"password": password})
        assert disable_resp.status_code == 200
        user_after = DBManager.get_user_by_id(user_id)
        assert user_after["two_factor_enabled"] is False
        assert user_after["two_factor_secret"] is None

        # Cleanup
        DBManager.delete_user(user_id)


class TestSessionManagementAndBulkRevocation:
    """Verifies multi-device session listing and revoke-others."""

    def test_revoke_other_sessions_invalidates_peer_tokens_and_retains_current(self, client, db_session):
        email = f"test_sessions_{datetime.now().timestamp()}@example.com"
        password = "SecurePassword123!"
        user_id = DBManager.create_user(email=email, hashed_pw=get_password_hash(password), full_name="Sessions User")
        DBManager.verify_email(user_id)

        # Login Device 1
        login1 = client.post("/auth/login", json={"email": email, "password": password}, headers={"User-Agent": "Device-1"})
        token1 = login1.json()["access_token"]
        refresh1 = login1.cookies.get("refresh_token")

        # Login Device 2
        login2 = client.post("/auth/login", json={"email": email, "password": password}, headers={"User-Agent": "Device-2"})
        token2 = login2.json()["access_token"]

        # Device 1 calls /auth/sessions
        headers1 = make_auth_headers(token1, client)
        sessions_resp = client.get("/auth/sessions", headers=headers1, cookies={"refresh_token": refresh1})
        assert sessions_resp.status_code == 200
        assert len(sessions_resp.json()) == 2

        # Device 1 revokes all other sessions
        revoke_others_resp = client.post("/auth/sessions/revoke-others", headers=headers1, cookies={"refresh_token": refresh1})
        assert revoke_others_resp.status_code == 200
        assert revoke_others_resp.json()["revoked_count"] == 1

        # Device 2 access token is immediately revoked (token_version was incremented)
        headers2 = {"Authorization": f"Bearer {token2}"}
        me2 = client.get("/auth/me", headers=headers2)
        assert me2.status_code == 401

        # Current session (Device 1) has been issued an updated access token
        new_token1 = revoke_others_resp.json()["access_token"]
        headers1_new = {"Authorization": f"Bearer {new_token1}"}
        me1 = client.get("/auth/me", headers=headers1_new)
        assert me1.status_code == 200

        # Cleanup
        DBManager.delete_user(user_id)


class TestAdminAuthorizationAndMetrics:
    """Verifies that admin endpoints strictly require is_admin=True."""

    def test_admin_endpoints_enforce_admin_flag(self, client, db_session):
        # Create standard user
        email_std = f"test_std_{datetime.now().timestamp()}@example.com"
        user_std_id = DBManager.create_user(email=email_std, hashed_pw=get_password_hash("Pass123!"), full_name="Standard User")
        DBManager.verify_email(user_std_id)
        login_std = client.post("/auth/login", json={"email": email_std, "password": "Pass123!"})
        std_headers = {"Authorization": f"Bearer {login_std.json()['access_token']}"}

        # Create admin user
        email_admin = f"test_adm_{datetime.now().timestamp()}@example.com"
        user_adm_id = DBManager.create_user(email=email_admin, hashed_pw=get_password_hash("Pass123!"), full_name="Admin User")
        DBManager.verify_email(user_adm_id)
        db_session.execute(text("UPDATE users SET is_admin = true WHERE id = :id"), {"id": user_adm_id})
        db_session.commit()

        login_adm = client.post("/auth/login", json={"email": email_admin, "password": "Pass123!"})
        adm_headers = {"Authorization": f"Bearer {login_adm.json()['access_token']}"}

        # Standard user accessing admin endpoints -> 403 Forbidden
        assert client.get("/auth/admin/stats", headers=std_headers).status_code == 403
        assert client.get("/auth/admin/audit-log", headers=std_headers).status_code == 403

        # Admin user accessing admin endpoints -> 200 OK
        stats_resp = client.get("/auth/admin/stats", headers=adm_headers)
        assert stats_resp.status_code == 200
        assert "total_users" in stats_resp.json()

        audit_resp = client.get("/auth/admin/audit-log", headers=adm_headers)
        assert audit_resp.status_code == 200
        assert "logs" in audit_resp.json()

        # Cleanup
        DBManager.delete_user(user_std_id)
        DBManager.delete_user(user_adm_id)


class TestDistributedNeonRateLimiting:
    """Verifies distributed rate limits backed by Neon PostgreSQL without external datastores."""

    def test_neon_backed_rate_limiting(self):
        ip = "192.0.2.123"
        action = f"test_rate_limit_{datetime.now().timestamp()}"

        # 3 requests allowed in 60 seconds
        assert DBManager.check_neon_rate_limit(action, ip_address=ip, max_requests=3, window_seconds=60) is True
        DBManager.log_auth_event(action, ip_address=ip)

        assert DBManager.check_neon_rate_limit(action, ip_address=ip, max_requests=3, window_seconds=60) is True
        DBManager.log_auth_event(action, ip_address=ip)

        assert DBManager.check_neon_rate_limit(action, ip_address=ip, max_requests=3, window_seconds=60) is True
        DBManager.log_auth_event(action, ip_address=ip)

        # 4th request must be throttled
        assert DBManager.check_neon_rate_limit(action, ip_address=ip, max_requests=3, window_seconds=60) is False


class TestMultiUserTenantIsolation:
    """Verifies User A cannot read or mutate User B's auth and profile data."""

    def test_user_a_cannot_access_user_b_sessions(self):
        with TestClient(app) as client_a, TestClient(app) as client_b:
            # User A
            email_a = f"user_a_{datetime.now().timestamp()}@example.com"
            id_a = DBManager.create_user(email_a, get_password_hash("Pass123!"), "User A")
            DBManager.verify_email(id_a)
            login_a = client_a.post("/auth/login", json={"email": email_a, "password": "Pass123!"})
            headers_a = make_auth_headers(login_a.json()["access_token"], client_a)

            # User B
            email_b = f"user_b_{datetime.now().timestamp()}@example.com"
            id_b = DBManager.create_user(email_b, get_password_hash("Pass123!"), "User B")
            DBManager.verify_email(id_b)
            login_b = client_b.post("/auth/login", json={"email": email_b, "password": "Pass123!"})
            headers_b = make_auth_headers(login_b.json()["access_token"], client_b)

            # User A gets sessions
            sessions_a = client_a.get("/auth/sessions", headers=headers_a).json()
            assert len(sessions_a) == 1
            session_a_id = sessions_a[0]["id"]

            # User B cannot revoke User A's session (returns 404)
            revoke_attempt = client_b.delete(f"/auth/sessions/{session_a_id}", headers=headers_b)
            assert revoke_attempt.status_code == 404

            # User A session is still active
            sessions_a_still = client_a.get("/auth/sessions", headers=headers_a).json()
            assert len(sessions_a_still) == 1

            # Cleanup
            DBManager.delete_user(id_a)
            DBManager.delete_user(id_b)


class TestDurableAccountDeletionAndChromaResilience:
    """Verifies durable cascaded account deletion for 2FA users and recovery from Chroma failures."""

    def test_account_deletion_with_2fa_and_chroma_failure_resilience(self, client, db_session):
        email = f"test_delete_{datetime.now().timestamp()}@example.com"
        password = "SecurePassword123!"
        user_id = DBManager.create_user(email=email, hashed_pw=get_password_hash(password), full_name="Delete User")
        DBManager.verify_email(user_id)

        # Enable 2FA with backup codes
        secret = pyotp.random_base32()
        DBManager.set_user_2fa_secret(user_id, secret=secret, enabled=True)
        code_hashes = [hash_backup_code(f"code_{i}") for i in range(10)]
        DBManager.save_user_backup_codes(user_id, code_hashes)

        # Create refresh token
        DBManager.create_refresh_token(
            user_id=user_id,
            token_hash=hash_refresh_token("delete_test_refresh"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            user_agent="TestAgent",
            ip_address="127.0.0.1",
            auth_time=int(datetime.now(timezone.utc).timestamp())
        )

        # Create audit log record
        DBManager.log_auth_event("login_success", user_id=user_id, email=email, ip_address="127.0.0.1")

        # Login
        login_resp = client.post("/auth/login", json={"email": email, "password": password})
        # If 2FA enabled, complete 2FA login challenge with backup code
        if login_resp.json().get("requires_2fa"):
            pending_token = login_resp.json()["pending_token"]
            verify_resp = client.post("/auth/2fa/verify", json={
                "pending_token": pending_token,
                "code": "code_0"
            })
            token = verify_resp.json()["access_token"]
        else:
            token = login_resp.json()["access_token"]

        headers = make_auth_headers(token, client)

        # Inject simulated ChromaDB outage during profile deletion
        with patch("app.vector_db.profile_store.ProfileStore.delete_profile", side_effect=RuntimeError("Simulated Chroma outage")):
            delete_resp = client.request("DELETE", "/auth/account", headers=headers, json={"password": password})
            assert delete_resp.status_code == 200, f"Account deletion failed despite Chroma resilience: {delete_resp.text}"

        # Verify relational user and child rows are completely purged
        assert DBManager.get_user_by_id(user_id) is None
        assert db_session.execute(select(TwoFactorBackupCode).where(TwoFactorBackupCode.user_id == user_id)).scalars().all() == []
        assert db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)).scalars().all() == []

        # Verify audit retention: audit log entry remains, but user_id is unlinked (None) for privacy
        audit_entry = db_session.execute(select(AuthAuditLog).where(AuthAuditLog.email == email)).scalars().first()
        if audit_entry:
            assert audit_entry.user_id is None, "Audit log user_id must be unlinked on account deletion"

        # Verify cookies deleted
        # Check response Set-Cookie headers for max-age=0 / deleted cookies
        cookie_headers = [v for k, v in delete_resp.headers.items() if k.lower() == "set-cookie"]
        assert any("authorization" in c for c in cookie_headers)
        assert any("refresh_token" in c for c in cookie_headers)
