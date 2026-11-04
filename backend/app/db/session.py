import logging
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

logger = logging.getLogger(__name__)


def mask_database_url(url: str) -> str:
    """Mask credentials in database URL to prevent exposing secrets in logs/errors."""
    if not url:
        return ""
    # Mask password between ':' and '@'
    return re.sub(r":([^:@]+)@", r":****@", url)


def resolve_database_hostaddr(url: str) -> str:
    """
    Ensure reliable host resolution for Neon PostgreSQL databases.
    If local/ISP DNS fails to resolve a Neon hostname (e.g. returning REFUSED or NXDOMAIN),
    resolves the endpoint via authoritative public DNS (8.8.8.8, 1.1.1.1) and injects
    'hostaddr' into the connection URL without modifying the original host header (preserving TLS SNI).
    """
    if not url or url.startswith("sqlite") or "hostaddr=" in url:
        return url

    try:
        import urllib.parse
        import socket
        parsed = urllib.parse.urlsplit(url)
        hostname = parsed.hostname
        if not hostname or hostname in ("localhost", "127.0.0.1", "::1"):
            return url

        # 1. Test standard system DNS resolution first
        try:
            port = parsed.port or 5432
            socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            return url  # System DNS functions normally
        except socket.gaierror as e:
            logger.info("System DNS failed to resolve %s (%s). Attempting fallback DNS resolution...", hostname, e)

        # 2. Query public fallback DNS resolvers (Google 8.8.8.8, Cloudflare 1.1.1.1)
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
            resolver.timeout = 3.0
            resolver.lifetime = 3.0
            answers = resolver.resolve(hostname, "A")
            if answers:
                resolved_ip = answers[0].address
                logger.info("Resolved database host %s -> %s via fallback DNS", hostname, resolved_ip)
                separator = "&" if "?" in url else "?"
                return f"{url}{separator}hostaddr={resolved_ip}"
        except Exception as dns_err:
            logger.warning("Fallback DNS resolution failed for %s: %s", hostname, dns_err)
    except Exception as parse_err:
        logger.warning("Error parsing database URL for host resolution: %s", parse_err)

    return url


def build_engine_url(raw_url: str) -> str:
    """Validate and configure PostgreSQL/Neon connection string with proper driver and TLS."""
    if not raw_url:
        raise ValueError(
            "DATABASE_URL is not set. Please configure DATABASE_URL in your environment or backend/.env file."
        )
    url = raw_url.strip()

    # Prefer psycopg v3 driver if plain postgresql:// is specified
    if url.startswith("postgresql://") and "+" not in url:
        try:
            import psycopg  # type: ignore
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        except ImportError:
            pass

    # Ensure required TLS/SSL mode for Neon and cloud-hosted PostgreSQL instances
    if ("neon.tech" in url or "amazonaws.com" in url) and "sslmode" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"

    # Ensure reliable host resolution if local DNS is filtered or broken
    url = resolve_database_hostaddr(url)

    return url


ENGINE_URL = build_engine_url(settings.DATABASE_URL)

is_sqlite = ENGINE_URL.startswith("sqlite")
is_neon_pooled = "pooler" in ENGINE_URL or "-pooler" in ENGINE_URL

if is_sqlite:
    engine = create_engine(
        ENGINE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
else:
    # Optimized for PostgreSQL/Neon startup behavior:
    # - fail fast instead of hanging indefinitely during server boot
    # - keep a small pool/timeout budget so app startup can continue if the DB is temporarily unreachable
    engine = create_engine(
        ENGINE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        future=True,
    )

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
    db_type = "sqlite" if ENGINE_URL.startswith("sqlite") else "postgresql"
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
