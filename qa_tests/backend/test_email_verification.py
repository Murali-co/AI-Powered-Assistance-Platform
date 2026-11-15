"""
Tests for Email Verification and Password Reset System
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.auth.models import DBManager
from app.auth.utils import generate_verification_token, get_password_hash, create_access_token
from app.config import settings

client = TestClient(app)

@pytest.fixture
def test_user():
    """Create a test user with unique email and yield for automatic cleanup"""
    email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
    password = "testpass123"
    full_name = "Test User"
    
    hashed_pw = get_password_hash(password)
    user_id = DBManager.create_user(
        email=email,
        hashed_pw=hashed_pw,
        full_name=full_name
    )
    
    yield {
        "id": user_id,
        "email": email,
        "password": password,
        "full_name": full_name
    }
    
    DBManager.delete_user(user_id)


@pytest.fixture
def verified_user(test_user):
    """Create a verified user"""
    DBManager.verify_email(test_user["id"])
    return test_user


@pytest.fixture
def verified_user_token(verified_user):
    """Get authenticated user token and ensure CSRF header is available on test client"""
    response = client.post("/auth/login", json={
        "email": verified_user["email"],
        "password": verified_user["password"]
    })
    token = response.json()["access_token"]
    csrf_token = response.cookies.get("csrf_token")
    client.headers.update({"X-CSRF-Token": csrf_token} if csrf_token else {})
    return token


# Test Email Verification Flow
class TestEmailVerification:
    
    def test_register_user_sends_verification_email(self):
        """Test that registration sends verification email"""
        email = f"newuser_{uuid.uuid4().hex[:8]}@example.com"
        response = client.post("/auth/register", json={
            "email": email,
            "password": "password123",
            "full_name": "New User"
        })
        
        assert response.status_code == 200
        assert "registration successful" in response.json()["message"].lower()
        
        # Verify user was created but not verified
        user = DBManager.get_user_by_email(email)
        assert user is not None
        assert user.get("email_verified") is False
        assert user.get("verification_token") is not None
        
        # Cleanup
        DBManager.delete_user(user["id"])
    
    def test_verify_email_with_valid_token(self, test_user):
        """Test email verification with valid token"""
        # Generate and set verification token
        token = generate_verification_token()
        expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        DBManager.set_verification_token(test_user["id"], token, expiry)
        
        # Verify email
        response = client.get(f"/auth/verify-email/{token}")
        
        assert response.status_code == 200
        assert response.json()["verified"] is True
        
        # Check user is now verified
        user = DBManager.get_user_by_id(test_user["id"])
        assert user["email_verified"] is True
        assert user["verification_token"] is None

    def test_verify_email_with_post_body(self, test_user):
        """Test email verification with POST request and JSON body"""
        token = generate_verification_token()
        expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        DBManager.set_verification_token(test_user["id"], token, expiry)
        
        response = client.post("/auth/verify-email", json={"token": token})
        assert response.status_code == 200
        assert response.json()["verified"] is True
        
        user = DBManager.get_user_by_id(test_user["id"])
        assert user["email_verified"] is True

    
    def test_verify_email_with_invalid_token(self):
        """Test email verification with invalid token"""
        response = client.get("/auth/verify-email/invalid_token_12345")
        
        assert response.status_code == 400
        assert "invalid or expired" in response.json()["detail"].lower()
    
    def test_verify_email_with_expired_token(self, test_user):
        """Test email verification with expired token"""
        # Set an expired token
        token = generate_verification_token()
        expiry = datetime.now(timezone.utc) - timedelta(hours=1)  # Expired
        DBManager.set_verification_token(test_user["id"], token, expiry)
        
        # Try to verify
        response = client.get(f"/auth/verify-email/{token}")
        
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()
    
    def test_resend_verification_email(self, test_user):
        """Test resending verification email"""
        response = client.post("/auth/resend-verification", json={
            "email": test_user["email"]
        })
        
        assert response.status_code == 200
        assert "if that account exists" in response.json()["message"].lower()
        
        # Verify new token was generated for unverified user
        user = DBManager.get_user_by_email(test_user["email"])
        assert user["verification_token"] is not None
    
    def test_resend_verification_for_already_verified_user(self, verified_user):
        """Test resending verification for already verified user returns uniform generic message"""
        response = client.post("/auth/resend-verification", json={
            "email": verified_user["email"]
        })
        
        assert response.status_code == 200
        assert "if that account exists" in response.json()["message"].lower()
    
    def test_login_allows_unverified_email(self, test_user):
        """Test that login allows users with unverified email"""
        response = client.post("/auth/login", json={
            "email": test_user["email"],
            "password": test_user["password"]
        })
        
        assert response.status_code == 200
        assert "access_token" in response.json()


# Test Password Reset Flow
class TestPasswordReset:
    
    def test_forgot_password_sends_reset_email(self, verified_user):
        """Test forgot password endpoint sends reset email"""
        response = client.post("/auth/forgot-password", json={
            "email": verified_user["email"]
        })
        
        assert response.status_code == 200
        assert "link has been sent" in response.json()["message"].lower()
    
    def test_reset_password_with_valid_token(self, verified_user):
        """Test password reset with valid token"""
        # Request forgot password to generate and store token
        forgot_res = client.post("/auth/forgot-password", json={"email": verified_user["email"]})
        assert forgot_res.status_code == 200

        from app.services.email_service import EmailService
        token = EmailService._last_sent_password_reset_token
        assert token is not None
        
        new_password = "newpassword123"
        response = client.post("/auth/reset-password", json={
            "token": token,
            "password": new_password
        })
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # Verify user can login with new password
        login_response = client.post("/auth/login", json={
            "email": verified_user["email"],
            "password": new_password
        })
        
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()
    
    def test_reset_password_with_invalid_token(self):
        """Test password reset with invalid token"""
        response = client.post("/auth/reset-password", json={
            "token": "invalid_token",
            "password": "newpassword123"
        })
        
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()
    
    def test_reset_password_with_expired_token(self, verified_user):
        """Test password reset with expired token"""
        # Set expired JWT token
        token = create_access_token(
            data={"user_id": verified_user["id"], "action": "reset_password"},
            expires_delta=timedelta(minutes=-15)  # Already expired
        )
        DBManager.set_reset_password_token(verified_user["id"], token, datetime.now(timezone.utc) - timedelta(minutes=15))
        
        response = client.post("/auth/reset-password", json={
            "token": token,
            "password": "newpassword123"
        })
        
        assert response.status_code == 400
        assert "expired or invalid" in response.json()["detail"].lower()


# Test Job Applications
class TestJobApplications:
    
    def test_apply_for_job(self, verified_user_token):
        """Test applying for a job"""
        response = client.post(
            "/apply/submit",
            json={
                "job_id": "job_123",
                "company": "Google",
                "title": "Senior Software Engineer",
                "location": "Mountain View, CA",
                "job_url": "https://google.com/jobs/123",
                "cover_letter": "I am interested in this position..."
            },
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        
        assert response.status_code == 200
        assert "logged successfully" in response.json()["message"].lower()
        assert response.json()["application_id"] is not None
    
    def test_apply_duplicate_job(self, verified_user_token):
        """Test applying for same job twice"""
        job_data = {
            "job_id": "job_456",
            "company": "Microsoft",
            "title": "Cloud Architect",
            "location": "Seattle, WA"
        }
        
        # First application
        response1 = client.post(
            "/apply/submit",
            json=job_data,
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        assert response1.status_code == 200
        
        # Second application for same job
        response2 = client.post(
            "/apply/submit",
            json=job_data,
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        
        # Should return valid application ID
        assert response2.status_code == 200
        assert response2.json()["application_id"] is not None
    
    def test_get_applied_jobs(self, verified_user_token):
        """Test retrieving applied jobs"""
        # Apply for a few jobs first
        for i in range(3):
            client.post(
                "/apply/submit",
                json={
                    "job_id": f"job_{i}",
                    "company": f"Company {i}",
                    "title": f"Position {i}"
                },
                headers={"Authorization": f"Bearer {verified_user_token}"}
            )
        
        response = client.get(
            "/apply/history",
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        
        assert response.status_code == 200
        assert len(response.json()) >= 3
    
    def test_update_application_status(self, verified_user_token):
        """Test updating application status"""
        # Create an application
        apply_response = client.post(
            "/apply/submit",
            json={
                "job_id": "job_789",
                "company": "Amazon",
                "title": "Solutions Architect"
            },
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        
        app_id = apply_response.json()["application_id"]
        
        # Update status
        response = client.patch(
            f"/apply/{app_id}/status?new_status=accepted",
            headers={"Authorization": f"Bearer {verified_user_token}"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
