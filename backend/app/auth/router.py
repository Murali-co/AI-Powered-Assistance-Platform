import asyncio
import time
import logging
import secrets
import hashlib
import hmac
import pyotp
from datetime import timedelta, datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query, Body
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from app.models.schemas import (
    UserRegister, UserLogin, Token, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest,
    PasswordResetResponse,
    TwoFactorConfirmRequest, TwoFactorDisableRequest, TwoFactorVerifyRequest
)
from app.auth.models import DBManager
from app.auth.utils import (
    get_password_hash, verify_password, create_access_token, get_current_user, get_current_admin_user,
    generate_verification_token, generate_reset_password_token, generate_refresh_token,
    hash_refresh_token, hash_token, generate_csrf_token, create_pending_2fa_token,
    decrypt_totp_secret, hash_backup_code, is_recent_auth, DUMMY_PASSWORD_HASH, get_client_ip
)
from app.config import settings
from app.services.email_service import EmailService
from app.utils.limiter import limiter
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import OperationalError as SQLAOperationalError, InterfaceError as SQLAInterfaceError, SQLAlchemyError
try:
    import psycopg
    PSYCOPG_OPERATIONAL_ERRORS = (psycopg.OperationalError,)
except ImportError:
    PSYCOPG_OPERATIONAL_ERRORS = ()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    token: Optional[str] = None

class AutoApprovePreferenceRequest(BaseModel):
    auto_approve_external_actions: bool
    password: Optional[str] = None
    totp_code: Optional[str] = None

class TwoFactorSetupRequest(BaseModel):
    password: Optional[str] = None

class TwoFactorRegenerateRequest(BaseModel):
    password: Optional[str] = None
    totp_code: Optional[str] = None

class DeleteAccountRequest(BaseModel):
    password: str


def check_sensitive_reauth(
    current_user: dict,
    full_user: dict,
    password: Optional[str] = None,
    totp_code: Optional[str] = None
) -> None:
    """
    Enforces re-authentication for sensitive actions (N4).
    Accepts valid password OR valid current TOTP code (if 2FA is enabled).
    Falls back to true is_recent_auth() only if neither was provided and auth was genuinely recent.
    """
    if password:
        if not verify_password(password, full_user["hashed_password"]):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password.")
        return

    if totp_code:
        if not full_user.get("two_factor_enabled"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled for this user.")
        raw_secret = DBManager.get_user_totp_secret(full_user["id"])
        if not raw_secret:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA configuration is invalid.")
        totp = pyotp.TOTP(raw_secret)
        clean_code = totp_code.strip().replace(" ", "").replace("-", "")
        if not totp.verify(clean_code, valid_window=1):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA verification code.")
        return

    if not is_recent_auth(current_user, max_minutes=15):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Recent authentication required. Please provide your password or current 2FA code."
        )


def parse_utc_datetime(val: Any) -> Optional[datetime]:
    """Helper to parse dates into timezone-aware UTC datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        cleaned = val.replace(" ", "T")
        try:
            dt = datetime.fromisoformat(cleaned)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def issue_tokens_and_set_cookies(
    user_id: int,
    user_email: str,
    request: Request,
    response: Response,
    auth_time: Optional[int] = None
) -> tuple:
    """Helper to generate access token, opaque refresh token, and CSRF token and set secure cookies.
    Persists auth_time with refresh token and access token (N4).
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    effective_auth_time = auth_time if auth_time is not None else now_ts

    token_data = {
        "user_id": user_id,
        "email": user_email,
        "type": "access",
        "auth_time": effective_auth_time
    }
    access_token = create_access_token(data=token_data)
    
    raw_refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    user_agent = request.headers.get("user-agent")
    ip_address = get_client_ip(request)
    
    # L2: Persistence verification — do not set refresh cookies if persistence fails!
    try:
        rt_id = DBManager.create_refresh_token(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            auth_time=effective_auth_time
        )
        if not rt_id:
            raise RuntimeError("Database did not return a valid session ID")
    except Exception as e:
        logger.error(f"[Auth] Failed to persist refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to establish a secure session at this time. Please try again."
        )
    
    csrf_tok = generate_csrf_token()
    
    # Set authorization cookie (15 min) - uses settings.is_production (R3)
    response.set_cookie(
        key="authorization",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    
    # Set refresh_token cookie (30 days) - uses settings.is_production (R3)
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/"
    )
    
    # Set csrf_token cookie (non-httpOnly for JS header echo) - uses settings.is_production (R3)
    response.set_cookie(
        key="csrf_token",
        value=csrf_tok,
        httponly=False,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/"
    )
    
    return access_token, raw_refresh_token, csrf_tok


@router.post("/register")
@limiter.limit("5/hour")
def register(user_data: UserRegister, request: Request):
    """Register a new user (H5 def handler)"""
    ip_addr = get_client_ip(request)
    ua = request.headers.get("user-agent")
    clean_email = user_data.email.strip().lower()
    clean_full_name = user_data.full_name.strip()

    # Check if user already exists
    existing_user = DBManager.get_user_by_email(clean_email)
    if existing_user:
        # Timing defense: equalize bcrypt hashing cost against user enumeration (R3)
        _ = get_password_hash(user_data.password)
        DBManager.log_auth_event(
            "registration_failed",
            email=clean_email,
            ip_address=ip_addr,
            user_agent=ua,
            detail="Registration failed: email already registered"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user_data.password)
    user_id = DBManager.create_user(
        email=clean_email,
        hashed_pw=hashed_password,
        full_name=clean_full_name
    )
    
    if not user_id:
        if DBManager.get_user_by_email(clean_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registering user"
        )
    
    # Generate email verification token (store hash in DB, send raw token)
    token = generate_verification_token()
    token_hash = hash_token(token)
    expiry = datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRY_HOURS)
    DBManager.set_verification_token(user_id, token_hash, expiry)
    
    # Send verification email synchronously in worker thread (H5)
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    email_sent = EmailService.send_verification_email(
        email=clean_email,
        full_name=clean_full_name,
        verification_link=verification_link
    )

    DBManager.log_auth_event(
        "user_registered",
        user_id=user_id,
        email=clean_email,
        ip_address=ip_addr,
        user_agent=ua,
        detail="User registered successfully"
    )

    response_payload = {
        "message": "Registration successful. Welcome to AI Powered Assistance Platform! A verification email has been sent to confirm your email address.",
        "email_sent": email_sent,
    }

    # Only expose development verification links when development mode is explicitly configured (M12)
    if not email_sent and settings.is_development:
        response_payload["verification_link"] = verification_link

    return response_payload


@router.post("/login", response_model=Token)
@limiter.limit("8/minute")
def login(credentials: UserLogin, request: Request, response: Response):
    """Login with email and password (H5 def handler)"""
    try:
        ip_addr = get_client_ip(request)
        ua = request.headers.get("user-agent")
        email = credentials.email.strip().lower()

        # Lockout check: 8 failed login attempts in last 15 mins for this target email (exact match)
        failed_attempts = DBManager.count_recent_failed_logins(email, minutes=15)
        if failed_attempts >= 8:
            DBManager.log_auth_event(
                "account_locked",
                user_id=None,
                email=email,
                ip_address=ip_addr,
                user_agent=ua,
                detail=f"Account locked due to {failed_attempts} failed attempts"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked due to multiple failed login attempts. Please try again in 15 minutes."
            )

        # Per-IP throttling check: protect against credential stuffing across multiple accounts
        if ip_addr:
            ip_failed = DBManager.count_recent_failed_logins_by_ip(ip_addr, minutes=15)
            if ip_failed >= 20:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts from this network. Please try again later."
                )

        # Progressive delay: dynamically slow down brute-force attacks on repeated failures (H4, R3)
        if failed_attempts >= 3:
            delay = min(0.25 * (2 ** (failed_attempts - 3)), 2.0)
            time.sleep(delay)

        user = DBManager.get_user_by_email(email)

        # Constant-time dummy verification using calibrated active scheme to prevent timing oracle (M10)
        password_to_verify = user["hashed_password"] if user else DUMMY_PASSWORD_HASH
        password_valid = verify_password(credentials.password, password_to_verify)

        if not user or not password_valid:
            DBManager.log_auth_event(
                "login_failed",
                user_id=user["id"] if user else None,
                email=email,
                ip_address=ip_addr,
                user_agent=ua,
                detail="Incorrect email or password"
            )
            new_failed_count = DBManager.count_recent_failed_logins(email, minutes=15)
            if new_failed_count >= 8:
                DBManager.log_auth_event(
                    "account_locked",
                    user_id=user["id"] if user else None,
                    email=email,
                    ip_address=ip_addr,
                    user_agent=ua,
                    detail="Account locked following failed login"
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.get("two_factor_enabled"):
            pending_token = create_pending_2fa_token(user_id=user["id"], email=user["email"])
            DBManager.log_auth_event(
                "2fa_challenge_issued",
                user_id=user["id"],
                email=email,
                ip_address=ip_addr,
                user_agent=ua,
                detail="2FA verification required"
            )
            return {
                "access_token": "",
                "token_type": "bearer",
                "requires_2fa": True,
                "pending_token": pending_token
            }

        access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
        DBManager.log_auth_event(
            "login_success",
            user_id=user["id"],
            email=user["email"],
            ip_address=ip_addr,
            user_agent=ua,
            detail="Login successful"
        )

        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except (SQLAOperationalError, SQLAInterfaceError, SQLAlchemyError, *PSYCOPG_OPERATIONAL_ERRORS) as e:
        logger.error("Database unavailable during login: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unavailable. Please try again shortly."
        )


@router.post("/refresh", response_model=Token)
@limiter.limit("60/minute")
def refresh(request: Request, response: Response):
    """
    Refresh access token using opaque refresh token cookie (H5 def handler).
    Implements atomic token rotation (H2), bounded grace period for concurrent requests, and replay detection.
    """
    try:
        raw_refresh_token = request.cookies.get("refresh_token")
        if not raw_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token cookie missing"
            )
        
        token_hash = hash_refresh_token(raw_refresh_token)
        record = DBManager.get_refresh_token_by_hash(token_hash)
        
        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = record["user_id"]
        user = DBManager.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User associated with refresh token not found"
            )

        now = datetime.now(timezone.utc)
        # Read persistent auth_time from refresh token row (N4)
        auth_time = record.get("auth_time")
        if auth_time is None:
            created_dt = parse_utc_datetime(record.get("created_at"))
            auth_time = int(created_dt.timestamp()) if created_dt else int(now.timestamp())

        # 1. EXPIRY CHECK
        expires_at_dt = parse_utc_datetime(record.get("expires_at"))
        if not expires_at_dt or now > expires_at_dt:
            DBManager.revoke_refresh_token(token_hash)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired"
            )

        # 2. REVOKED TOKEN CHECK (Replay Attack vs Bounded Grace Window)
        if record.get("revoked_at") is not None:
            revoked_at_dt = parse_utc_datetime(record["revoked_at"])
            grace_window = getattr(settings, "REFRESH_TOKEN_GRACE_SECONDS", 15)
            
            # Check if rotated within allowed grace window
            is_within_grace = (
                revoked_at_dt is not None and
                grace_window > 0 and
                (now - revoked_at_dt).total_seconds() <= grace_window
            )

            if is_within_grace and record.get("replaced_by"):
                # Bounded grace policy: Concurrent request with a recently rotated token.
                # Retrieve the active successor token and return an access token for it.
                successor = DBManager.get_refresh_token_by_hash(record["replaced_by"])
                successor_expires = parse_utc_datetime(successor.get("expires_at")) if successor else None
                
                if successor and successor.get("revoked_at") is None and successor_expires and successor_expires > now:
                    succ_auth_time = successor.get("auth_time") or record.get("auth_time") or auth_time
                    token_data = {"user_id": user["id"], "email": user["email"], "type": "access", "auth_time": succ_auth_time}
                    access_token = create_access_token(data=token_data)
                    
                    response.set_cookie(
                        key="authorization",
                        value=f"Bearer {access_token}",
                        httponly=True,
                        secure=settings.is_production,
                        samesite="strict",
                        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        path="/"
                    )
                    return {"access_token": access_token, "token_type": "bearer"}

            # Outside grace window (or no valid successor): Replay attack detected!
            DBManager.revoke_all_user_refresh_tokens(user_id)
            response.delete_cookie("refresh_token", path="/")
            response.delete_cookie("authorization", path="/")
            response.delete_cookie("csrf_token", path="/")
            DBManager.log_auth_event(
                "login_failed",
                user_id=user_id,
                email=user["email"],
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                detail="Replay attack detected: revoked refresh token reused"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected. All sessions revoked."
            )

        # 3. ATOMIC TOKEN ROTATION (H2)
        new_raw_refresh = generate_refresh_token()
        new_token_hash = hash_refresh_token(new_raw_refresh)
        new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        user_agent = request.headers.get("user-agent")
        ip_address = get_client_ip(request)

        try:
            new_rt_id = DBManager.rotate_refresh_token_atomic(
                old_token_hash=token_hash,
                new_token_hash=new_token_hash,
                user_id=user_id,
                expires_at=new_expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
                auth_time=auth_time
            )
        except Exception as e:
            logger.error(f"[Auth] Failed during atomic token rotation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to refresh authentication session at this time. Please try again."
            )

        if not new_rt_id:
            # Atomic collision: lost the race to a concurrent request that consumed it simultaneously
            # Check grace window immediately
            fresh_record = DBManager.get_refresh_token_by_hash(token_hash)
            if fresh_record and fresh_record.get("replaced_by"):
                successor = DBManager.get_refresh_token_by_hash(fresh_record["replaced_by"])
                successor_expires = parse_utc_datetime(successor.get("expires_at")) if successor else None
                if successor and successor.get("revoked_at") is None and successor_expires and successor_expires > now:
                    succ_auth_time = successor.get("auth_time") or record.get("auth_time") or auth_time
                    token_data = {"user_id": user["id"], "email": user["email"], "type": "access", "auth_time": succ_auth_time}
                    access_token = create_access_token(data=token_data)
                    response.set_cookie(
                        key="authorization",
                        value=f"Bearer {access_token}",
                        httponly=True,
                        secure=settings.is_production,
                        samesite="strict",
                        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        path="/"
                    )
                    return {"access_token": access_token, "token_type": "bearer"}

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token already consumed"
            )

        # Persistence succeeded! Now safe to issue tokens and set cookies (L2)
        token_data = {"user_id": user["id"], "email": user["email"], "type": "access", "auth_time": auth_time}
        access_token = create_access_token(data=token_data)
        csrf_tok = generate_csrf_token()

        response.set_cookie(
            key="authorization",
            value=f"Bearer {access_token}",
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/"
        )
        response.set_cookie(
            key="refresh_token",
            value=new_raw_refresh,
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/"
        )
        response.set_cookie(
            key="csrf_token",
            value=csrf_tok,
            httponly=False,
            secure=settings.is_production,
            samesite="strict",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/"
        )

        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except (SQLAOperationalError, SQLAInterfaceError, SQLAlchemyError, *PSYCOPG_OPERATIONAL_ERRORS) as e:
        logger.error("Database unavailable during refresh: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unavailable. Please try again shortly."
        )


@router.post("/logout")
def logout(request: Request, response: Response):
    """
    Logout endpoint (H5 def handler). Revokes refresh token in database and clears cookies.
    """
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        token_hash = hash_refresh_token(raw_refresh_token)
        DBManager.revoke_refresh_token(token_hash)
        
    response.delete_cookie(key="authorization", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/sessions")
@limiter.limit("60/minute")
def list_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    """
    List user's active, non-revoked refresh token sessions (H5 def handler).
    Includes is_current flag comparing token_hash to request refresh token.
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    sessions = DBManager.get_active_user_sessions(current_user["id"])
    return [
        {
            "id": s["id"],
            "created_at": s["created_at"],
            "expires_at": s["expires_at"],
            "user_agent": s.get("user_agent"),
            "ip_address": s.get("ip_address"),
            "is_current": (s["token_hash"] == current_hash) if current_hash else False,
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
@limiter.limit("60/minute")
def revoke_session(session_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """
    Revoke a specific session by ID ("log out other devices") (H5 def handler).
    Disallows revoking current session from this endpoint (force /logout for current session).
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    target_session = DBManager.get_refresh_token_by_id(session_id)
    if target_session and target_session.get("token_hash") == current_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your current session from this endpoint. Please use /auth/logout instead."
        )

    revoked = DBManager.revoke_session_by_id(session_id, current_user["id"])
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already revoked"
        )
    return {"message": "Session revoked successfully"}


@router.post("/sessions/revoke-others")
@limiter.limit("30/minute")
def revoke_other_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Revoke all active sessions for current user EXCEPT the current session (H5 def handler).
    """
    raw_refresh = request.cookies.get("refresh_token")
    current_hash = hash_refresh_token(raw_refresh) if raw_refresh else None

    count = DBManager.revoke_other_user_sessions(current_user["id"], current_hash)
    DBManager.log_auth_event(
        "sessions_revoked",
        user_id=current_user["id"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=f"Revoked {count} other active sessions"
    )
    return {"message": f"Successfully logged out {count} other device(s).", "revoked_count": count}


@router.get("/me", response_model=UserOut)
def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile (H5 def handler)"""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "created_at": current_user["created_at"],
        "two_factor_enabled": current_user.get("two_factor_enabled", False),
        "auto_approve_external_actions": current_user.get("auto_approve_external_actions", False),
        "is_admin": current_user.get("is_admin", False),
        "email_verified": bool(current_user.get("email_verified", False)),
    }


@router.post("/forgot-password", response_model=dict)
@limiter.limit("3/hour")
def forgot_password(request: Request, body: ForgotPasswordRequest):
    """Request a password reset link for the user (H5 def handler, R3 timing defense)."""
    ip_addr = get_client_ip(request)
    ua = request.headers.get("user-agent")

    user = DBManager.get_user_by_email(body.email)
    if user:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRY_MINUTES)
        reset_token = generate_reset_password_token()
        token_hash = hash_token(reset_token)
        DBManager.set_reset_password_token(user["id"], token_hash, expiry)

        EmailService.send_password_reset_email(
            email=body.email,
            full_name=user.get("full_name", "User"),
            reset_link=f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        )
        DBManager.log_auth_event("password_reset_requested", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail=f"Reset requested for {body.email}")
    else:
        # Timing defense: equalize crypto/hash execution time to prevent account enumeration (R3)
        dummy_token = generate_reset_password_token()
        _ = hash_token(dummy_token)
        _ = verify_password("dummy_password", DUMMY_PASSWORD_HASH)
        DBManager.log_auth_event("password_reset_requested", user_id=None, ip_address=ip_addr, user_agent=ua, detail=f"Reset requested for unknown email {body.email}")

    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", response_model=PasswordResetResponse)
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest):
    """Reset password using a one-time cryptographically random token (H5 def handler, R3 rate limit)."""
    ip_addr = get_client_ip(request)
    ua = request.headers.get("user-agent")

    raw_token = body.token.strip()
    token_hash = hash_token(raw_token)

    # Perform lookup strictly using SHA-256 hash of submitted opaque token (N2)
    user = DBManager.get_user_by_reset_token(token_hash)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used or is invalid."
        )

    stored_token = user.get("reset_password_token")
    if not stored_token or not hmac.compare_digest(stored_token, token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used or is invalid."
        )

    expiry = user.get("reset_password_token_expiry")
    if expiry:
        expiry_dt = None
        if isinstance(expiry, str):
            val = expiry.replace(" ", "T")
            try:
                if "+" in val or "-" in val.split("T")[-1]:
                    expiry_dt = datetime.fromisoformat(val)
                else:
                    expiry_dt = datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        expiry_dt = datetime.strptime(expiry, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
        else:
            expiry_dt = expiry
            if expiry_dt and expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

        if expiry_dt and datetime.now(timezone.utc) > expiry_dt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired or invalid reset token.")

    user_id = user["id"]
    hashed_password = get_password_hash(body.password)
    DBManager.reset_password(user_id, hashed_password)

    # H6: Revoke ALL existing refresh token sessions across all devices
    DBManager.revoke_all_user_refresh_tokens(user_id)

    DBManager.log_auth_event(
        "password_reset_completed",
        user_id=user_id,
        email=user.get("email"),
        ip_address=ip_addr,
        user_agent=ua,
        detail="Password reset successfully; all active sessions revoked."
    )

    return {"message": "Password reset successfully! You can now log in with your new password.", "success": True}


@router.get("/verify-email")
@router.get("/verify-email/{token}")
@router.post("/verify-email")
@router.post("/verify-email/{token}")
def verify_email(
    request: Request,
    response: Response,
    token: Optional[str] = None,
    token_query: Optional[str] = Query(None, alias="token"),
    body: Optional[VerifyEmailRequest] = None
):
    """Verify email address with token (supports path param, query param, or POST body) (H5 def handler)"""
    body_token = body.token if body else None
    active_token = (token or token_query or body_token or "").strip()
    if not active_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is required"
        )
    token_hash = hash_token(active_token)
    # Perform lookup strictly using SHA-256 hash of submitted opaque token (N2)
    user = DBManager.get_user_by_verification_token(token_hash)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    stored_token = user.get("verification_token")
    if not stored_token or not hmac.compare_digest(stored_token, token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
        
    # Check expiry
    expiry = user.get("verification_token_expiry")
    if expiry:
        expiry_dt = None
        if isinstance(expiry, str):
            val = expiry.replace(" ", "T")
            try:
                if "+" in val or "-" in val.split("T")[-1]:
                    expiry_dt = datetime.fromisoformat(val)
                else:
                    expiry_dt = datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        expiry_dt = datetime.strptime(expiry, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
        elif isinstance(expiry, datetime):
            expiry_dt = expiry
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                
        if expiry_dt and datetime.now(timezone.utc) > expiry_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired"
            )
            
    DBManager.verify_email(user["id"])
    access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    DBManager.log_auth_event("login_success", user_id=user["id"], ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"), detail="Email verified and logged in")
    return {
        "verified": True,
        "message": "Email verified successfully!",
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/resend-verification")
@limiter.limit("5/hour")
def resend_verification(request: Request, body: ResendVerificationRequest):
    """Resend email verification token (H5 def handler, R3 timing defense)"""
    clean_email = body.email.strip().lower()
    user = DBManager.get_user_by_email(clean_email)
    verification_link = None
    email_sent = False
    if user and not user.get("email_verified"):
        token = generate_verification_token()
        token_hash = hash_token(token)
        expiry = datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRY_HOURS)
        DBManager.set_verification_token(user["id"], token_hash, expiry)
        
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        email_sent = EmailService.send_verification_email(
            email=user["email"],
            full_name=user["full_name"],
            verification_link=verification_link
        )
    else:
        # Timing defense: equalize crypto/hash execution time to prevent account enumeration (R3)
        dummy_token = generate_verification_token()
        _ = hash_token(dummy_token)
        _ = verify_password("dummy", DUMMY_PASSWORD_HASH)
        
    res = {"message": "If that account exists and needs verification, an email has been sent."}
    if verification_link and not email_sent and settings.is_development:
        res["verification_link"] = verification_link
    return res


@router.get("/admin/stats")
def get_admin_stats(req: Request, current_user: dict = Depends(get_current_admin_user)):
    ip_addr = get_client_ip(req)
    ua = req.headers.get("user-agent")
    DBManager.log_auth_event("admin_action", user_id=current_user["id"], ip_address=ip_addr, user_agent=ua, detail="Accessed admin stats")
    return DBManager.get_admin_metrics()


@router.get("/admin/audit-log")
@limiter.limit("60/minute")
def get_admin_audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_admin_user)
):
    """Admin-only audit log endpoint with filtering and pagination (H5 def handler)"""
    ip_addr = get_client_ip(request)
    ua = request.headers.get("user-agent")
    DBManager.log_auth_event("admin_action", user_id=current_user["id"], ip_address=ip_addr, user_agent=ua, detail="Accessed admin audit log")

    return DBManager.get_admin_audit_logs(
        page=page,
        per_page=per_page,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date
    )


# ===== 2FA ENDPOINTS =====
@router.post("/2fa/setup")
@limiter.limit("10/minute")
def setup_2fa(
    request: Request,
    body: Optional[TwoFactorSetupRequest] = None,
    current_user: dict = Depends(get_current_user)
):
    """Generate TOTP secret and otpauth URL for 2FA setup. Stores pending secret on server (H5 def handler, N4)."""
    if current_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled on this account.")

    # Sensitive change: Require recent authentication or password verification (M1, N4)
    full_user = DBManager.get_user_by_id(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if full_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled on this account.")

    check_sensitive_reauth(current_user, full_user, password=body.password if body else None)

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(name=current_user["email"], issuer_name="AI Powered Assistance Platform")

    # Store generated secret on server as pending state (enabled=False); do not trust client-supplied secret (N4)
    DBManager.set_user_2fa_secret(current_user["id"], secret=secret, enabled=False)

    return {
        "secret": secret,
        "otpauth_url": otpauth_url
    }


@router.post("/2fa/confirm")
@limiter.limit("10/minute")
def confirm_2fa(body: TwoFactorConfirmRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Verify setup code against server pending secret, enable 2FA with authenticated encryption at rest (H5 def handler, M1, N4)"""
    if current_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled on this account.")

    full_user = DBManager.get_user_by_id(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if full_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled on this account.")

    # Re-authentication check: password verification or recent auth (N4)
    check_sensitive_reauth(current_user, full_user, password=body.password)

    # Retrieve pending secret stored on server; do NOT trust secret supplied by client (N4)
    raw_secret = DBManager.get_user_totp_secret(current_user["id"])
    if not raw_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA setup has not been initiated. Please call /auth/2fa/setup first."
        )

    totp = pyotp.TOTP(raw_secret)
    clean_code = body.code.strip().replace(" ", "").replace("-", "")
    if not totp.verify(clean_code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    # Generate 10 strong 16-hex-character (64-bit entropy) backup codes (M1)
    backup_codes = [secrets.token_hex(8).upper() for _ in range(10)]
    code_hashes = [hash_backup_code(bc) for bc in backup_codes]

    # Store encrypted TOTP secret at rest with authenticated encryption (M1, N5)
    DBManager.set_user_2fa_secret(current_user["id"], secret=raw_secret, enabled=True)
    DBManager.save_user_backup_codes(current_user["id"], code_hashes)
    DBManager.log_auth_event("2fa_enabled", user_id=current_user["id"], ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"), detail="2FA enabled successfully")

    return {
        "message": "Two-factor authentication enabled successfully. Store your backup codes safely in a secure password manager. If you lose access to your authenticator, backup codes are required for account recovery.",
        "backup_codes": backup_codes
    }


@router.post("/2fa/disable")
@limiter.limit("10/minute")
def disable_2fa(body: TwoFactorDisableRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Disable 2FA after verifying current user password (H5 def handler, M1)"""
    full_user = DBManager.get_user_by_id(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    password_ok = verify_password(body.password, full_user["hashed_password"])
    if not password_ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password.")

    DBManager.set_user_2fa_secret(current_user["id"], secret=None, enabled=False)
    DBManager.save_user_backup_codes(current_user["id"], [])
    DBManager.log_auth_event("2fa_disabled", user_id=current_user["id"], ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"), detail="2FA disabled successfully")

    return {"message": "Two-factor authentication disabled successfully."}


@router.post("/2fa/backup-codes/regenerate")
@limiter.limit("5/minute")
def regenerate_backup_codes(
    request: Request,
    body: Optional[TwoFactorRegenerateRequest] = None,
    current_user: dict = Depends(get_current_user)
):
    """Regenerate 10 new backup codes with keyed hashes for 2FA-enabled user (H5 def handler, M1, N4)"""
    if not current_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA must be enabled to generate backup codes.")

    full_user = DBManager.get_user_by_id(current_user["id"])
    if not full_user or not full_user.get("two_factor_enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA must be enabled to generate backup codes.")

    pwd = body.password if body else None
    totp = body.totp_code if body else None
    check_sensitive_reauth(current_user, full_user, password=pwd, totp_code=totp)

    backup_codes = [secrets.token_hex(8).upper() for _ in range(10)]
    code_hashes = [hash_backup_code(bc) for bc in backup_codes]
    DBManager.save_user_backup_codes(current_user["id"], code_hashes)
    DBManager.log_auth_event("2fa_backup_codes_regenerated", user_id=current_user["id"], ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent"), detail="2FA backup codes regenerated")

    return {
        "message": "New backup codes generated successfully. Store them safely.",
        "backup_codes": backup_codes
    }


@router.post("/2fa/verify", response_model=Token)
@limiter.limit("10/minute")
def verify_2fa(body: TwoFactorVerifyRequest, request: Request, response: Response):
    """Verify 2FA TOTP code or backup code after login challenge (H5 def handler, M1)"""
    ip_addr = get_client_ip(request)
    ua = request.headers.get("user-agent")

    try:
        payload = jwt.decode(body.pending_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        purpose = payload.get("purpose")
        token_type = payload.get("type")
        if user_id is None or (purpose != "2fa_pending" and token_type != "2fa_pending"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA session token.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA verification session expired. Please log in again.")

    # Failed attempt limit per user (M1)
    failed_attempts = DBManager.count_recent_failed_2fa(user_id, minutes=15)
    if failed_attempts >= 5:
        DBManager.log_auth_event("account_locked_2fa", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="Too many failed 2FA verification attempts")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed 2FA verification attempts. Please wait 15 minutes before trying again."
        )

    user = DBManager.get_user_by_id(user_id)
    if not user or not user.get("two_factor_enabled") or not user.get("two_factor_secret"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled for this user.")

    clean_code = body.code.strip().replace(" ", "").replace("-", "")
    raw_secret = DBManager.get_user_totp_secret(user_id)
    if not raw_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA configuration is invalid.")

    totp = pyotp.TOTP(raw_secret)
    current_time = datetime.now(timezone.utc)
    matched_step = None

    # Handle reasonable clock drift (+-1 time step, 30s each)
    for offset in (-1, 0, 1):
        step_time = current_time + timedelta(seconds=offset * totp.interval)
        if hmac.compare_digest(totp.at(step_time), clean_code):
            matched_step = totp.timecode(step_time)
            break

    is_valid = False
    if matched_step is not None:
        # Prevent reuse of a TOTP time step (M1)
        last_step = user.get("last_totp_step")
        if last_step is not None and matched_step <= last_step:
            DBManager.log_auth_event("2fa_failed", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="Replay of TOTP time step detected")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This 2FA code has already been used. Please wait for the next time window."
            )
        DBManager.update_user_last_totp_step(user_id, matched_step)
        is_valid = True
    else:
        # Fallback check: try atomic backup code consumption
        is_valid = DBManager.verify_and_consume_backup_code(user_id, clean_code)

    if not is_valid:
        DBManager.log_auth_event("2fa_failed", user_id=user_id, ip_address=ip_addr, user_agent=ua, detail="Invalid 2FA verification code")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA code or backup code.")

    access_token, raw_refresh, csrf_tok = issue_tokens_and_set_cookies(user["id"], user["email"], request, response)
    DBManager.log_auth_event("login_success", user_id=user["id"], ip_address=ip_addr, user_agent=ua, detail="2FA login successful")

    return {"access_token": access_token, "token_type": "bearer"}


@router.patch("/preferences/auto-approve-external")
def update_auto_approve_preference(
    payload: AutoApprovePreferenceRequest,
    current_user: dict = Depends(get_current_user)
):
    """Toggle auto_approve_external_actions preference with validated model and reauth (H5 def handler, M13, N4)."""
    full_user = DBManager.get_user_by_id(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    check_sensitive_reauth(current_user, full_user, password=payload.password, totp_code=payload.totp_code)

    auto_approve = payload.auto_approve_external_actions
    DBManager.update_auto_approve_external_actions(current_user["id"], auto_approve)
    DBManager.log_auth_event(
        user_id=current_user["id"],
        event_type="user_preference_updated",
        detail=f"Updated auto_approve_external_actions to {auto_approve}"
    )
    return {
        "status": "success",
        "auto_approve_external_actions": auto_approve
    }


@router.delete("/account")
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user)
):
    """
    F-010: Authenticated user account deletion with mandatory password verification.
    Cascades removal of all user data across relational tables, ChromaDB vector collections
    (user_profiles and applications), and local uploads, revoking active sessions.
    """
    user_id = current_user["id"]
    full_user = DBManager.get_user_by_id(user_id)
    if not full_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(payload.password, full_user["hashed_password"]):
        ip_addr = get_client_ip(request)
        ua = request.headers.get("user-agent")
        DBManager.log_auth_event(
            "delete_account_failed",
            user_id=user_id,
            ip_address=ip_addr,
            user_agent=ua,
            detail="Incorrect password for account deletion"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password. Account deletion aborted."
        )

    # Execute cascaded deletion across tables, vectors, and files
    DBManager.delete_user(user_id)

    # Clear authentication cookies
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")

    return {
        "status": "success",
        "message": "Your account and all associated personal data have been permanently deleted."
    }



