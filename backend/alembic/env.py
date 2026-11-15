from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load environment variables from backend/.env or root .env
try:
    from dotenv import load_dotenv
    for env_candidate in [os.path.join(backend_dir, ".env"), os.path.join(os.path.dirname(backend_dir), ".env")]:
        if os.path.exists(env_candidate):
            load_dotenv(env_candidate)
            break
except ImportError:
    pass

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None and not os.environ.get("TESTING"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import all SQLAlchemy models to ensure complete metadata registration
from app.db.models import Base
import app.orchestrator.models  # Register orchestrator workflows & tasks
target_metadata = Base.metadata

# Neon supports direct connections (DIRECT_URL) for schema migrations
# and pooled connections (DATABASE_URL) for application traffic.
# Check for CLI -x url=... argument, programmatic config option, or environment variables
x_args = context.get_x_argument(as_dictionary=True)
cli_x_url = x_args.get('url')
custom_url = config.get_main_option('sqlalchemy.url')
is_default_ini_url = (custom_url in ('postgresql://user:password@localhost:5432/ai_platform_db', '', None))

if cli_x_url:
    raw_url = cli_x_url
elif custom_url and not is_default_ini_url:
    raw_url = custom_url
elif os.environ.get('ALEMBIC_DATABASE_URL'):
    raw_url = os.environ.get('ALEMBIC_DATABASE_URL')
else:
    raw_url = os.environ.get('DIRECT_URL') or os.environ.get('DATABASE_URL')
    if not raw_url:
        try:
            from app.config import settings
            raw_url = getattr(settings, 'DIRECT_URL', None) or settings.DATABASE_URL
        except Exception:
            raw_url = custom_url

if raw_url:
    from app.db.session import build_engine_url
    url = build_engine_url(raw_url)
    config.set_main_option('sqlalchemy.url', url)


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Compatibility update for legacy 0006 revision ID if present
        try:
            from sqlalchemy import text, inspect
            insp = inspect(connection)
            if 'alembic_version' in insp.get_table_names():
                connection.execute(
                    text("UPDATE alembic_version SET version_num = '0006_refresh_and_audit_log' WHERE version_num = '0006_refresh_tokens_and_audit_log'")
                )
                connection.commit()
        except Exception:
            pass

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
