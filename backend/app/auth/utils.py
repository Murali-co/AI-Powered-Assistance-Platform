import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import logging
from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.auth.models import DBManager

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Constant-time dummy password hash (M10): pre-computed using active algorithm
DUMMY_PASSWORD_HASH = pwd_context.hash("dummy_timing_pad_ai_platform_2026")

def get_totp_fernet() -> MultiFernet:
    """Retrieve MultiFernet authenticated encryption keys for 2FA secrets (M1, N5).
    Supports key rotation with primary TWO_FACTOR_ENCRYPTION_KEY and legacy derived fallback.
    """
    fernets = []
    custom_key = getattr(settings, "TWO_FACTOR_ENCRYPTION_KEY", None)
    if custom_key:
        key_list = [k.strip() for k in custom_key.split(",") if k.strip()]
        for k in key_list:
            try:
                fernets.append(Fernet(k.encode("utf-8") if isinstance(k, str) else k))
            except Exception as e:
                logger.warning(f"Failed to load configured TWO_FACTOR_ENCRYPTION_KEY: {e}")

    # Primary key derived deterministically from SECRET_KEY using platform salt
    primary_derived = base64.urlsafe_b64encode(
        hashlib.sha256(b"ai-powered-assistance-platform-2fa-secret-encryption:" + settings.SECRET_KEY.encode("utf-8")).digest()
    )
    fernets.append(Fernet(primary_derived))

    # Backward-compatible fallback key decoded from base64 so existing secrets remain decryptable
    legacy_salt = base64.b64decode(b"Y29nbmlzLTJmYS1zZWNyZXQtZW5jcnlwdGlvbjo=")
    legacy_derived = base64.urlsafe_b64encode(
        hashlib.sha256(legacy_salt + settings.SECRET_KEY.encode("utf-8")).digest()
    )
    fernets.append(Fernet(legacy_derived))
    return MultiFernet(fernets)

def is_valid_base32_totp_secret(val: str) -> bool:
    """Detect legacy plaintext TOTP secrets by valid Base32 format (N5)."""
    if not val or not isinstance(val, str):
        return False
    clean = val.strip().replace(" ", "").upper()
    if len(clean) < 16 or len(clean) > 64:
        return False
    if val.startswith("gAAAA"):
        return False
    valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=")
    if not all(c in valid_chars for c in clean):
        return False
    try:
        padding = (8 - len(clean) % 8) % 8
        decoded = base64.b32decode(clean + "=" * padding, casefold=True)
        return len(decoded) >= 10
    except Exception:
        return False

def encrypt_totp_secret(secret: Optional[str]) -> Optional[str]:
    """Encrypt TOTP secret at rest using authenticated encryption (M1, N5)."""
    if not secret:
        return None
    fernet = get_totp_fernet()
    return fernet.encrypt(secret.strip().encode("utf-8")).decode("utf-8")

def decrypt_totp_secret(encrypted_secret: Optional[str]) -> Optional[str]:
    """Decrypt TOTP secret at rest using MultiFernet.
    Detects legacy plaintext secrets by valid Base32 format.
    Never treats failed decryption ciphertext as a plaintext TOTP secret (N5).
    """
    if not encrypted_secret:
        return None
    # 1. If it's a legacy unencrypted secret in valid Base32 format, return it directly
    if is_valid_base32_totp_secret(encrypted_secret):
        return encrypted_secret.strip().replace(" ", "").upper()

    # 2. Otherwise attempt authenticated decryption with MultiFernet
    fernet = get_totp_fernet()
    try:
        return fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.error(f"[Auth] Failed to decrypt 2FA secret: {e}")
        # Never treat failed decryption ciphertext as a plaintext TOTP secret (N5)
        return None

def hash_backup_code(code: str) -> str:
    """Generate HMAC-SHA256 keyed hash for backup codes using dedicated pepper (M1, N5)."""
    normalized = code.strip().replace("-", "").upper()
    pepper = getattr(settings, "TWO_FACTOR_BACKUP_CODE_PEPPER", None)
    if pepper:
        key = pepper.encode("utf-8")
    else:
        key = hashlib.sha256(b"ai-powered-assistance-platform-2fa-backup-pepper:" + settings.SECRET_KEY.encode("utf-8")).digest()
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

def legacy_pepper_hash_backup_code(code: str) -> str:
    """Legacy HMAC-SHA256 keyed with initial pepper for backward compatibility."""
    normalized = code.strip().replace("-", "").upper()
    legacy_pepper = base64.b64decode(b"Y29nbmlzLTJmYS1iYWNrdXAtcGVwcGVyOg==")
    key = hashlib.sha256(legacy_pepper + settings.SECRET_KEY.encode("utf-8")).digest()
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

def legacy_secret_key_hash_backup_code(code: str) -> str:
    """Legacy HMAC-SHA256 keyed directly with SECRET_KEY before separate pepper (N5)."""
    normalized = code.strip().replace("-", "").upper()
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

def legacy_hash_backup_code(code: str) -> str:
    """Legacy unkeyed SHA-256 for backward compatibility with initial backup codes."""
    return hashlib.sha256(code.strip().replace("-", "").upper().encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if "type" not in to_encode:
        to_encode["type"] = "access"
    if "token_type" not in to_encode:
        to_encode["token_type"] = "access"
    now_dt = datetime.now(timezone.utc)
    to_encode.setdefault("iat", int(now_dt.timestamp()))
    if expires_delta:
        expire = now_dt + expires_delta
    else:
        expire = now_dt + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_password_reset_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a scoped JWT token for password reset (type: reset_password)."""
    delta = expires_delta or timedelta(minutes=settings.PASSWORD_RESET_EXPIRY_MINUTES)
    return create_access_token({"user_id": user_id, "type": "reset_password", "action": "reset_password"}, expires_delta=delta)

def create_verification_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a scoped JWT token for email verification (type: verification)."""
    delta = expires_delta or timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRY_HOURS)
    return create_access_token({"user_id": user_id, "type": "verification", "action": "verify_email"}, expires_delta=delta)

def create_pending_2fa_token(user_id: int, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a scoped pending-2FA challenge token (type: 2fa_pending)."""
    delta = expires_delta or timedelta(minutes=5)
    return create_access_token({"user_id": user_id, "email": email, "type": "2fa_pending", "purpose": "2fa_pending"}, expires_delta=delta)

def generate_verification_token() -> str:
    """Generate a secure verification token"""
    return secrets.token_urlsafe(32)

def generate_reset_password_token() -> str:
    """Generate a secure password reset token"""
    return secrets.token_urlsafe(32)

def generate_refresh_token() -> str:
    """Generate a long-lived opaque refresh token"""
    return secrets.token_urlsafe(48)

def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a token for secure storage"""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def hash_refresh_token(token: str) -> str:
    """Compute SHA-256 hash of a refresh token"""
    return hash_token(token)

def generate_csrf_token() -> str:
    """Generate a secure CSRF token"""
    return secrets.token_urlsafe(32)

def decode_access_token_payload(token_or_header: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode and validate a Bearer access token (N7).
    Validates token cryptographically using settings.ALGORITHM and SECRET_KEY.
    Requires payload.get('type') == 'access'.
    Reused across main.py (CSRF validation) and limiter.py (user-keyed rate limiting).
    Returns decoded token dictionary on success, None on invalid/expired/non-access token.
    """
    if not token_or_header or not isinstance(token_or_header, str):
        return None
    raw = token_or_header.strip()
    if raw.startswith("Bearer "):
        token = raw[7:].strip()
    else:
        token = raw
    if not token or token in ("undefined", "null", ""):
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") == "access":
            return payload
    except Exception:
        pass
    return None

def get_client_ip(request: Request) -> str:
    """Extract client IP supporting trusted reverse proxies, direct connections, and test clients (N3).
    Only trusts X-Forwarded-For when settings.TRUST_PROXY_HEADERS is True.
    For single-proxy setups, uses the rightmost forwarded address.
    Falls back to request.client.host, or 'testclient' for unit test clients.
    """
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Single-proxy setup: rightmost forwarded address was appended by our trusted proxy
            ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            if ips:
                return ips[-1]
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return "testclient"

oauth2_scheme_opt = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_opt)
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Normalize undefined/null string tokens from JS frontend
    if token in ("undefined", "null", ""):
        token = None
        
    # Check cookie fallback if header not present
    if not token:
        cookie_val = request.cookies.get("authorization")
        if cookie_val and cookie_val.startswith("Bearer "):
            token = cookie_val[7:]
            
    if not token or token in ("undefined", "null", ""):
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # Immediate token purpose / type verification (C3): Require type == "access"
        token_type = payload.get("type")
        if token_type != "access":
            if token_type == "2fa_pending" or payload.get("purpose") == "2fa_pending":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Full authentication required. Please complete 2FA verification."
                )
            raise credentials_exception

        raw_user_id = payload.get("user_id")
        if raw_user_id is None:
            raise credentials_exception
        user_id: int = int(raw_user_id)
        email: str = str(payload.get("email") or "")
        token_iat: Optional[int] = payload.get("iat")
    except JWTError:
        raise credentials_exception
        
    user = await run_in_threadpool(DBManager.get_user_by_id, user_id)
    if user is None:
        raise credentials_exception

    safe_user = sanitize_user_dict(user)
    # Attach genuine session authentication timestamp from token payload (N4)
    # Fall back to token_iat only if auth_time is not explicitly present (legacy compatibility)
    safe_user["auth_time"] = payload.get("auth_time") or token_iat
    return safe_user

SENSITIVE_USER_FIELDS = {
    "hashed_password",
    "two_factor_secret",
    "reset_password_token",
    "reset_password_token_expiry",
    "verification_token",
    "verification_token_expiry",
}

def sanitize_user_dict(user: Dict[str, Any]) -> Dict[str, Any]:
    """Return a safe public-user object omitting sensitive secrets and reset tokens (M13)."""
    return {k: v for k, v in user.items() if k not in SENSITIVE_USER_FIELDS}

def is_recent_auth(current_user: Dict[str, Any], max_minutes: int = 15) -> bool:
    """Check if the user was authenticated recently (within max_minutes)."""
    auth_time = current_user.get("auth_time")
    if not auth_time:
        return False
    now_ts = datetime.now(timezone.utc).timestamp()
    return (now_ts - auth_time) <= (max_minutes * 60)

async def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges"
        )
    return current_user
