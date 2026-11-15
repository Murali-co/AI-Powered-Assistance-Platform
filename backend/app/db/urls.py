"""Connection URL validation without creating an engine or reading credentials."""
from sqlalchemy.engine import make_url


def build_engine_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        raise ValueError("DATABASE_URL must configure Neon PostgreSQL.")
    try:
        url = make_url(raw_url.strip())
    except Exception:
        raise ValueError("Invalid PostgreSQL connection URL.") from None
    if url.get_backend_name() != "postgresql":
        raise ValueError("Only PostgreSQL is supported; SQLite and other relational backends are forbidden.")
    url = url.set(drivername="postgresql+psycopg")
    host = (url.host or "").lower()
    if not host.endswith(".neon.tech"):
        raise ValueError("DATABASE_URL must identify a Neon PostgreSQL endpoint.")
    if set(url.query) & {"host", "hostaddr", "port", "dbname", "service", "servicefile", "user", "password"}:
        raise ValueError("Database routing and credentials must be specified in the URL authority, not query overrides.")
    mode = url.query.get("sslmode", "require")
    if mode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Neon PostgreSQL requires TLS (sslmode=require or stronger).")
    url = url.update_query_dict({"sslmode": mode})
    return url.render_as_string(hide_password=False)


def mask_database_url(raw_url: str) -> str:
    """Redact userinfo and all query values, including tokens and TLS passwords."""
    if not raw_url:
        return ""
    try:
        url = make_url(raw_url)
        url = url.set(username="REDACTED", password="REDACTED")
        url = url.update_query_dict({key: "REDACTED" for key in url.query})
        return url.render_as_string(hide_password=True)
    except Exception:
        return "[invalid database URL redacted]"
