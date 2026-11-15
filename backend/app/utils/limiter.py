import os
from fastapi import Request
from slowapi import Limiter
from app.config import settings

def get_rate_limit_key(request: Request) -> str:
    """
    Compute rate limit key based on authenticated user identity where available,
    or trusted client IP when unauthenticated (M6).
    Prevents sharing a single IP bucket across all proxy users.
    """
    # 1. Authenticated user identity if already attached to request state
    user = getattr(request.state, "user", None)
    if isinstance(user, dict) and user.get("id"):
        return f"user:{user['id']}"

    # 2. Extract user ID from Bearer token if present (N7)
    from app.auth.utils import decode_access_token_payload, get_client_ip
    auth_header = request.headers.get("authorization") or ""
    if auth_header:
        payload = decode_access_token_payload(auth_header)
        if payload:
            user_id = payload.get("user_id") or payload.get("sub")
            if user_id:
                return f"user:{user_id}"

    # 3. Client IP fallback: shared client-IP helper (N3)
    client_ip = get_client_ip(request)
    return f"ip:{client_ip}"

is_testing = (
    os.getenv("TESTING", "").lower() in ("true", "1", "yes")
    or os.getenv("ENVIRONMENT", "").lower() in ("test", "testing")
    or not getattr(settings, "RATE_LIMIT_ENABLED", True)
)

storage_uri = getattr(settings, "RATE_LIMIT_STORAGE_URL", None) or "memory://"

limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=storage_uri,
    enabled=not is_testing
)

