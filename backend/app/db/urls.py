"""Connection URL validation without creating an engine or reading credentials."""
from sqlalchemy.engine import make_url
from sqlalchemy import event


def connection_args(raw_url: str) -> dict:
    """Bound dead-socket waits as well as initial connection establishment.

    connect_timeout alone does not bound an established connection's TCP wait.
    Server statement deadlines are installed per transaction, since Neon
    pooled connections reject statement_timeout in startup options.
    """
    build_engine_url(raw_url)
    args = {'connect_timeout': 10, 'keepalives': 1, 'keepalives_idle': 10,
            'keepalives_interval': 5, 'keepalives_count': 3, 'tcp_user_timeout': 30000}
    return args


def configure_statement_timeout(engine, milliseconds: int):
    if type(milliseconds) is not int or not 1000 <= milliseconds <= 600000:
        raise ValueError('DATABASE_STATEMENT_TIMEOUT_MS must be from 1000 to 600000.')
    @event.listens_for(engine, 'begin')
    def bound_transaction(connection):
        # SET LOCAL belongs to this transaction and is reset at commit or
        # rollback. It cannot leak to another user through transaction pooling.
        connection.exec_driver_sql(f'SET LOCAL statement_timeout = {milliseconds}')


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
