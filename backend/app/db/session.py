import logging
import re
import socket
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from app.db.urls import build_engine_url, mask_database_url
from app.db.dns import configure_neon_dns

# Prefer IPv4 over unreachable IPv6 routes to prevent connection timeouts with dual-stack hosts (e.g. Neon)
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_preferred_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 if v4 else res

socket.getaddrinfo = _ipv4_preferred_getaddrinfo

logger = logging.getLogger(__name__)


ENGINE_URL = build_engine_url(settings.DATABASE_URL)
is_neon_pooled = "pooler" in ENGINE_URL or "-pooler" in ENGINE_URL

# Sized connection pool across API & worker processes for Neon PostgreSQL
engine = create_engine(
    ENGINE_URL,
    pool_size=10,
    max_overflow=5,
    pool_recycle=300,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args={"connect_timeout": 10},
    future=True,
)
configure_neon_dns(engine, settings.NEON_DNS_FALLBACK)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db_session():
    """FastAPI dependency for yielding database sessions with guaranteed closure."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Reusable database dependency alias for FastAPI endpoints
get_db = get_db_session


def sanitize_database_error(error_msg: str) -> str:
    """Mask any database credentials, passwords, or tokens in error strings."""
    if not error_msg:
        return ""
    # Mask user:password@host
    sanitized = re.sub(r":([^:@\s]+)@", r":****@", error_msg)
    # Mask password="..." or password '...' or : password
    sanitized = re.sub(r"password\s*(=|is|:)\s*['\"]?[^'\s\",]+['\"]?", r"password\1****", sanitized, flags=re.IGNORECASE)
    # Strip sensitive trailing values from authentication failures
    if "password authentication failed" in sanitized.lower():
        sanitized = re.sub(r"(password authentication failed for user '[^']+'?)(.*)", r"\1", sanitized, flags=re.IGNORECASE)
    return sanitized


def check_database_connection() -> dict:
    """
    Test database connection by executing SELECT 1 and inspecting required tables.
    Never exposes raw credentials.
    """
    from sqlalchemy import text, inspect
    db_type = "postgresql"
    masked = mask_database_url(ENGINE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # Inspect tables
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        
        # Verify ALL required tables defined across ORM models
        from app.db.models import Base
        try:
            import app.orchestrator.models  # type: ignore
        except ImportError:
            pass
        required_tables = sorted(list(Base.metadata.tables.keys()))
        missing_tables = [t for t in required_tables if t not in existing_tables]

        return {
            "healthy": True,
            "connected": True,
            "schema_ready": len(missing_tables) == 0,
            "database_type": db_type,
            "masked_url": masked,
            "missing_tables": missing_tables,
            "error": None
        }
    except Exception as e:
        error_msg = str(e)
        sanitized_error = sanitize_database_error(error_msg)
        return {
            "healthy": False,
            "connected": False,
            "schema_ready": False,
            "database_type": db_type,
            "masked_url": masked,
            "missing_tables": None,
            "error": sanitized_error
        }
