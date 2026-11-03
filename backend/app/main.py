import hmac
import logging
import os
import time
import uuid
from pathlib import Path
from urllib.parse import unquote
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from typing import Dict, Any, Optional, List
from app.config import settings

# Configure service logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("ai_platform.backend")

# Routers
from app.auth.router import router as auth_router
from app.resume.router import router as resume_router, calculate_ats_score
from app.jobs.router import router as jobs_router
from app.jobs.saved_router import router as saved_jobs_router
from app.applications.router import router as apply_router
from app.rag.router import router as rag_router
from app.copilot.router import router as copilot_router
from app.interview.router import router as interview_router
from app.market.router import router as market_router
from app.notifications.router import router as notifications_router
from app.settings.router import router as settings_router
from app.profile.router import router as profile_router
from app.llm.router import router as llm_router
from app.feedback.router import router as feedback_router
from app.analytics.router import router as analytics_router
from app.orchestrator.router import router as orchestrator_router
from app.jobs.scheduler import start_scheduler, shutdown_scheduler

# Optional RateLimit handling
try:
    from slowapi.errors import RateLimitExceeded  # type: ignore
    from slowapi import _rate_limit_exceeded_handler  # type: ignore
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    RateLimitExceeded = None
    _rate_limit_exceeded_handler = None

# Optional Limiter
try:
    from app.utils.limiter import limiter
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    limiter = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle: clean startup verification and graceful shutdown.
    Avoids duplicate initialization or destructive wipe of persistent resources.
    """
    logger.info("AI Powered Assistance Platform Backend starting up...")

    # 1. Non-destructive database check
    db_ready = False
    try:
        from app.db.session import check_database_connection
        db_check = check_database_connection()
        if db_check["healthy"]:
            logger.info("✅ Database connectivity verified.")
            if not db_check["schema_ready"]:
                logger.warning(
                    f"⚠️ Database schema missing tables: {db_check['missing_tables']}. "
                    "Run 'alembic upgrade head' to apply pending migrations."
                )
            else:
                db_ready = True
        else:
            logger.error(f"❌ Database connection failed during startup: {db_check['error']}")
    except Exception as e:
        logger.error(f"❌ Database startup check error: {e}")

    # 2. ChromaDB safe initialization
    try:
        from app.vector_db.chroma_client import ChromaDBClient
        ChromaDBClient.initialize_collections()
        logger.info("✅ ChromaDB collections verified.")
    except Exception as e:
        logger.warning(f"⚠️ ChromaDB collection initialization deferred/failed: {e}")

    # 3. Start APScheduler and recover background jobs when database is reachable
    if db_ready:
        try:
            from app.utils.bg_jobs import recover_pending_or_stale_jobs
            recover_pending_or_stale_jobs(stale_minutes=30)
        except Exception as e:
            logger.warning(f"⚠️ Background job crash recovery warning: {e}")

        try:
            start_scheduler()
        except Exception as e:
            logger.warning(f"⚠️ Failed to start background scheduler on startup: {e}")
    else:
        logger.warning("⚠️ Skipping APScheduler startup because the database is unavailable or schema is incomplete.")

    yield

    # Shutdown sequence
    logger.info("AI Powered Assistance Platform Backend shutting down...")
    try:
        shutdown_scheduler()
    except Exception as e:
        logger.warning(f"Warning during scheduler shutdown: {e}")

    try:
        from app.db.session import engine
        engine.dispose()
        logger.info("Database connection pool disposed.")
    except Exception as e:
        logger.warning(f"Warning during database engine disposal: {e}")


app = FastAPI(
    title="AI Powered Assistance Platform API",
    description="AI Powered Assistance Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Proxy headers support (N3)
if getattr(settings, "TRUST_PROXY_HEADERS", False):
    try:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        trusted_hosts = [h.strip() for h in getattr(settings, "FORWARDED_ALLOW_IPS", "127.0.0.1").split(",") if h.strip()]
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)
    except Exception as e:
        logger.warning(f"Could not initialize ProxyHeadersMiddleware: {e}")

# Rate limiting
if LIMITER_AVAILABLE and limiter:
    app.state.limiter = limiter
    if SLOWAPI_AVAILABLE and RateLimitExceeded and _rate_limit_exceeded_handler:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Origins Setup
def get_allowed_origins() -> list[str]:
    raw = [org.strip() for org in settings.CORS_ORIGINS.split(",") if org.strip()]
    if getattr(settings, "FRONTEND_URL", None):
        f_origin = settings.FRONTEND_URL.rstrip("/")
        if f_origin and f_origin not in raw:
            raw.append(f_origin)
    return raw

origins = get_allowed_origins()

def get_cors_headers(request: Request) -> dict:
    """Helper to ensure error responses receive appropriate CORS headers (M5)."""
    origin = request.headers.get("origin")
    if not origin:
        return {}
    allowed = get_allowed_origins()
    if "*" in allowed or origin in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    return {}

EXEMPT_CSRF_PATHS = {
    "/auth/login", "/auth/register", "/auth/refresh",
    "/auth/forgot-password", "/auth/reset-password", "/auth/resend-verification",
    "/auth/2fa/verify", "/auth/verify-email", "/auth/account",
    "/health", "/health/live", "/health/ready", "/health/services", "/health/db",
    "/api/health/ollama", "/", "/docs", "/openapi.json", "/redoc"
}


@app.middleware("http")
async def security_and_correlation_middleware(request: Request, call_next):
    # Correlation ID (M4)
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = req_id

    # 1. Double-submit CSRF Protection for state-changing HTTP methods (M5)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        path = request.url.path.rstrip("/") or "/"
        norm_path = path.replace("/api/v1", "") if path.startswith("/api/v1") else path
        if norm_path not in EXEMPT_CSRF_PATHS and not any(norm_path.startswith(p) for p in ["/docs", "/openapi.json", "/redoc", "/health"]):
            # If Bearer authentication is used, bypass CSRF only after cryptographically validating the token (M5, N7)
            from app.auth.utils import decode_access_token_payload
            auth_header = request.headers.get("authorization") or ""
            payload = decode_access_token_payload(auth_header)
            is_valid_bearer = bool(payload and (payload.get("user_id") or payload.get("sub")))

            csrf_cookie = request.cookies.get("csrf_token")
            # Bypass CSRF only for valid Bearer token without ambient session cookie
            if is_valid_bearer and not csrf_cookie:
                pass
            else:
                csrf_header = request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token")
                if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
                    cors_h = get_cors_headers(request)
                    resp_headers = {"X-Request-ID": req_id, **cors_h}
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF token validation failed", "request_id": req_id},
                        headers=resp_headers
                    )

    response = await call_next(request)

    # Correlation ID in response headers
    response.headers["X-Request-ID"] = req_id

    # 2. Security Headers (M5)
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # CSP: adjust for API documentation routes to allow Swagger UI & Redoc scripts/styles (M5)
    req_path = request.url.path.rstrip("/") or "/"
    if any(req_path.startswith(doc_p) for doc_p in ["/docs", "/redoc", "/openapi.json"]):
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
            "connect-src 'self';"
        )
    else:
        ollama_origin = settings.OLLAMA_BASE_URL.rstrip("/")
        frontend_origin = settings.FRONTEND_URL.rstrip("/")
        csp_policy = (
            f"default-src 'self'; "
            f"connect-src 'self' {ollama_origin} {frontend_origin}; "
            f"img-src 'self' data:; "
            f"script-src 'self' 'unsafe-inline'; "
            f"style-src 'self' 'unsafe-inline'"
        )
    response.headers["Content-Security-Policy"] = csp_policy

    return response


# CORS Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth_router)
app.include_router(resume_router)
ats_compat_router = APIRouter(prefix="/ats", tags=["ats"])
ats_compat_router.add_api_route("/score", calculate_ats_score, methods=["POST"])
app.include_router(ats_compat_router)
app.include_router(jobs_router)
app.include_router(saved_jobs_router)
app.include_router(apply_router)
app.include_router(rag_router)
app.include_router(copilot_router)
app.include_router(interview_router)
app.include_router(market_router)
app.include_router(notifications_router)
app.include_router(settings_router)
app.include_router(profile_router)
app.include_router(llm_router)
app.include_router(feedback_router)
app.include_router(analytics_router)
app.include_router(orchestrator_router)


from sqlalchemy.exc import OperationalError as SQLAOperationalError, InterfaceError as SQLAInterfaceError
try:
    import psycopg
    PSYCOPG_OPERATIONAL = (psycopg.OperationalError,)
except ImportError:
    PSYCOPG_OPERATIONAL = ()


# Controlled Database Service Unavailable Handler
@app.exception_handler(SQLAOperationalError)
@app.exception_handler(SQLAInterfaceError)
async def database_connectivity_exception_handler(request: Request, exc: Exception):
    from app.db.session import sanitize_database_error
    req_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or str(uuid.uuid4())
    logger.error("DATABASE SERVICE UNAVAILABLE on %s %s [ReqID: %s]: %s", request.method, request.url.path, req_id, sanitize_database_error(str(exc)))
    cors_h = get_cors_headers(request)
    resp_headers = {"X-Request-ID": req_id, **cors_h}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Database service is currently unavailable. Please try again shortly.",
            "request_id": req_id
        },
        headers=resp_headers
    )

if PSYCOPG_OPERATIONAL:
    app.add_exception_handler(psycopg.OperationalError, database_connectivity_exception_handler)


# Secure Global Exception Handler (M4)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    req_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or str(uuid.uuid4())
    logger.exception("CRITICAL ERROR on %s %s [ReqID: %s]: %s", request.method, request.url.path, req_id, exc)

    cors_h = get_cors_headers(request)
    resp_headers = {"X-Request-ID": req_id, **cors_h}

    if settings.is_development:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": str(exc),
                "traceback": traceback.format_exc(),
                "request_id": req_id
            },
            headers=resp_headers
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred. Please contact administrator.",
            "request_id": req_id
        },
        headers=resp_headers
    )


# Root Health Check
@app.get("/")
async def root_health_check():
    return {
        "status": "healthy",
        "service": "AI Powered Assistance Platform",
        "version": "1.0.0"
    }


# Dashboard Overview Endpoint
from app.profile.router import get_dashboard_overview
from app.auth.utils import get_current_user

@app.get("/dashboard/overview")
async def dashboard_overview_endpoint(current_user: dict = Depends(get_current_user)):
    return await get_dashboard_overview(current_user)


# ============================================================================
# STANDARDIZED HEALTH CHECK ENDPOINTS (PHASE G)
# ============================================================================

# ============================================================================
# STANDARDIZED HEALTH CHECK ENDPOINTS (PHASE G / M10 / M12)
# ============================================================================

@app.get("/health/live")
async def liveness_check():
    """
    Minimal public liveness probe (M10): reports process vitality without diagnostics.
    """
    return {
        "status": "alive",
        "service": "AI Powered Assistance Platform",
        "timestamp": time.time()
    }


@app.get("/health/ready")
async def readiness_check():
    """
    Minimal public readiness probe (M10): checks core DB readiness without disclosing
    internal connection strings, schema details, or stack traces.
    """
    from app.db.session import check_database_connection
    db_status = check_database_connection()

    is_ready = bool(db_status.get("healthy") and db_status.get("schema_ready"))
    db_payload = {"status": "connected"} if is_ready else {
        "status": "unavailable",
        "error": db_status.get("error", "Database unavailable") if settings.is_development else "Database unavailable"
    }
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "database": db_payload
    }
    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return payload


# Diagnostic caching to prevent resource exhaustion from expensive checks (M10/M12)
_DIAGNOSTICS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "payload": None, "is_unhealthy": False}
DIAGNOSTICS_CACHE_TTL = 30.0


@app.get("/health/services")
async def services_health_check(current_user: dict = Depends(get_current_user)):
    """
    Detailed service status (restricted to authorized users - M10/M12).
    Results are cached for 30 seconds to prevent resource exhaustion.
    """
    global _DIAGNOSTICS_CACHE
    now = time.time()
    ttl = 0.0 if os.environ.get("TESTING") == "true" else DIAGNOSTICS_CACHE_TTL
    if _DIAGNOSTICS_CACHE["payload"] is not None and (now - _DIAGNOSTICS_CACHE["timestamp"]) < ttl:
        if _DIAGNOSTICS_CACHE["is_unhealthy"]:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=_DIAGNOSTICS_CACHE["payload"])
        return _DIAGNOSTICS_CACHE["payload"]

    from app.db.session import check_database_connection
    from app.llm.ollama_client import OllamaClient
    from app.vector_db.chroma_client import ChromaDBClient
    from app.vector_db.embedder import check_embedding_status
    from app.jobs.scheduler import get_scheduler_status

    # 1. Database (Mandatory)
    db_res = await run_in_threadpool(check_database_connection)
    db_healthy = db_res["healthy"] and db_res["schema_ready"]

    # 2. ChromaDB (Local persistent)
    chroma_res = await run_in_threadpool(ChromaDBClient.check_health)

    # 3. Embedding model
    emb_res = await run_in_threadpool(check_embedding_status)

    # 4. Ollama & Qwen3 model
    ollama_res = await OllamaClient.check_service_status()

    # 5. Background scheduler
    sched_res = await run_in_threadpool(get_scheduler_status)

    if not db_res["healthy"]:
        overall = "unhealthy"
    elif not chroma_res["healthy"] or not emb_res["healthy"] or not ollama_res["model_available"] or not db_res["schema_ready"]:
        overall = "degraded"
    else:
        overall = "healthy"

    payload = {
        "status": overall,
        "services": {
            "database": {
                "mandatory": True,
                "status": "healthy" if db_healthy else ("schema_incomplete" if db_res["healthy"] else "unhealthy"),
                "connected": db_res["connected"],
                "schema_ready": db_res["schema_ready"],
                "database_type": db_res["database_type"],
                "missing_tables": db_res["missing_tables"],
                "error": db_res["error"]
            },
            "ollama": {
                "mandatory": False,
                "status": ollama_res.get("status", "unknown"),
                "reachable": ollama_res.get("reachable", False),
                "configured_model": ollama_res.get("configured_model", settings.OLLAMA_MODEL),
                "model_available": ollama_res.get("model_available", False),
                "message": ollama_res.get("message") or ollama_res.get("error"),
                "install_command": ollama_res.get("install_command"),
                "available_models": ollama_res.get("available_models", [])
            },
            "chromadb": {
                "mandatory": False,
                "status": "healthy" if chroma_res["healthy"] else "unhealthy",
                "collections": chroma_res["collections"],
                "error": chroma_res["error"]
            },
            "embeddings": {
                "mandatory": False,
                "status": "healthy" if emb_res["healthy"] else "unhealthy",
                "model": emb_res["model_name"],
                "error": emb_res["error"]
            },
            "scheduler": {
                "mandatory": False,
                "status": "running" if sched_res["running"] else "stopped",
                "jobs": sched_res["jobs"]
            }
        }
    }

    is_unhealthy = (overall == "unhealthy")
    _DIAGNOSTICS_CACHE = {"timestamp": now, "payload": payload, "is_unhealthy": is_unhealthy}

    if is_unhealthy:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return payload


# Backwards compatibility endpoints (restricted to authorized users - M10/M12)
@app.get("/health/db")
async def db_health_check(current_user: dict = Depends(get_current_user)):
    """Backwards-compatible database health check."""
    from app.db.session import check_database_connection
    res = check_database_connection()
    if not res["healthy"]:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "connected": False,
                "database": res["database_type"],
                "error": res["error"]
            }
        )
    return {
        "status": "healthy",
        "connected": True,
        "database": res["database_type"]
    }


@app.get("/health")
async def detailed_health_check(current_user: dict = Depends(get_current_user)):
    """Backwards-compatible consolidated health check (authorized - M10/M12)."""
    return await services_health_check(current_user=current_user)


@app.get("/api/health/ollama")
async def ollama_health_detail(current_user: dict = Depends(get_current_user)):
    """Detailed Ollama health endpoint (authorized - M10/M12)."""
    from app.llm.ollama_client import OllamaClient
    status_info = await OllamaClient.check_service_status()
    return {
        "ollama_reachable": status_info["reachable"],
        "configured_model": status_info["configured_model"],
        "model_available": status_info["model_available"],
        "available_models": status_info["available_models"],
        "details": status_info["message"],
    }


# Optional SPA Frontend Serving
STATIC_DIR = (Path(__file__).resolve().parent.parent / "static").resolve()

API_PREFIXES = (
    "api/", "dashboard/", "auth/", "resume/", "ats/", "jobs/", "apply/", "rag/", "copilot/", 
    "interview/", "market/", "notifications/", "settings/", 
    "profile/", "llm/", "feedback/", "analytics/", "orchestrator/", "health"
)

if os.environ.get("SERVE_STATIC_FRONTEND") == "true" or STATIC_DIR.is_dir():
    @app.get("/{catchall:path}", include_in_schema=False)
    async def serve_react_app(catchall: str):
        # 1. Reject API and backend routes with explicit JSON 404
        normalized_path = catchall.strip("/")
        if (
            catchall in ("api", "health")
            or normalized_path in ("api", "health")
            or any(
                (catchall.startswith(prefix) or normalized_path.startswith(prefix))
                for prefix in API_PREFIXES
                if not (prefix == "dashboard/" and normalized_path == "dashboard")
            )
        ):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})

        decoded_path = unquote(catchall)
        path_segments = [p for p in decoded_path.replace("\\", "/").split("/") if p]

        # 2. Reject directory traversal attempts and hidden files
        if (
            ".." in catchall
            or ".." in decoded_path
            or any(part.startswith(".") for part in path_segments)
            or any(part in ("etc", "proc", "sys", "var", "dev") for part in path_segments)
        ):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})

        # 3. Resolve candidate static asset path safely
        try:
            candidate = (STATIC_DIR / decoded_path.lstrip("/")).resolve()
            is_safe = candidate.is_relative_to(STATIC_DIR)
        except (ValueError, Exception):
            is_safe = False

        if not is_safe or candidate.name.startswith(".env") or any(part.startswith(".env") for part in candidate.parts):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})

        # 4. If static file exists inside STATIC_DIR, serve it
        if candidate.is_file():
            return FileResponse(str(candidate))

        # 5. If requested path looks like a file asset (has a suffix/extension) but does not exist, return 404
        if candidate.suffix:
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})

        # 6. SPA Fallback: Serve index.html for legitimate frontend page routes
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))

        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Frontend assets not found."})
