import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Silence telemetry flags early
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "False"

logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Base directory paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Load environment files deterministically from PROJECT_ROOT/.env and BACKEND_DIR/.env
try:
    from dotenv import load_dotenv
    for env_path in [PROJECT_ROOT / ".env", BACKEND_DIR / ".env"]:
        if env_path.is_file():
            load_dotenv(env_path, override=False)
except ImportError:
    pass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
    from pydantic import field_validator, model_validator  # type: ignore
    IS_PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseSettings, validator, root_validator  # type: ignore
    IS_PYDANTIC_V2 = False
    SettingsConfigDict = None


def resolve_app_path(path_str: str) -> str:
    """
    Resolve relative paths deterministically against PROJECT_ROOT so that
    whether the backend is launched from repository root or backend/,
    storage paths point to the exact same persistent location.
    """
    if not path_str:
        return ""
    p = Path(path_str)
    if p.is_absolute():
        return str(p)
    # In test mode or when running specific test data directories
    if os.environ.get("TESTING") == "true" or path_str.startswith("./test_") or path_str.startswith("test_"):
        candidate_cwd = (Path.cwd() / path_str).resolve()
        return str(candidate_cwd)
    return str((PROJECT_ROOT / path_str).resolve())


class Settings(BaseSettings):
    DEBUG: bool = False

    # JWT Authentication
    SECRET_KEY: str = "dev-secret-key-for-local-testing-ai-platform-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # 15 minutes access token
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30    # 30 days refresh token
    REFRESH_TOKEN_GRACE_SECONDS: int = 30  # 30-second duplicate-refresh grace window (H2)

    # Two-Factor Authentication Encryption Key & Pepper (M1, N5)
    TWO_FACTOR_ENCRYPTION_KEY: Optional[str] = None
    TWO_FACTOR_BACKUP_CODE_PEPPER: Optional[str] = None

    # Ollama Local LLM
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3:14b"
    OLLAMA_TIMEOUT: float = 120.0
    # OLLAMA_NUM_CTX: Default 4096. Hardware evaluation (R2/M8): NVIDIA RTX 4050 GPU has 6141MB VRAM
    # (5375MB free). Installed model 'qwen3:14b' weight blob is ~8.7GB, exceeding GPU VRAM.
    # Raising to 8192 requires ~4GB KV cache (~12.7GB total), causing OOM on 6GB GPU and 7GB free RAM.
    # Maintained at 4096; dynamically configurable via OLLAMA_NUM_CTX environment variable.
    OLLAMA_NUM_CTX: int = 4096
    # Local LLM Runtime (Ollama exclusively)
    LLM_PROVIDER: str = "ollama"

    # Database & Vector Storage
    CHROMA_PATH: str = "./data/chroma_db"
    ANONYMIZED_TELEMETRY: bool = False
    CHROMA_ANONYMIZED_TELEMETRY: bool = False
    DATABASE_URL: str = "sqlite:///./data/ai_platform.db"
    DIRECT_URL: str = ""

    # Upload folder
    UPLOAD_DIR: str = "./uploads"

    # Environment
    ENVIRONMENT: str = "development"

    # CORS -- include the standard local dev ports used by the frontend and Vite reload server.
    CORS_ORIGINS: str = ",".join(DEFAULT_CORS_ORIGINS)

    # Email Service (Resend)
    RESEND_API_KEY: str = ""
    FRONTEND_URL: str = "http://localhost:3000"

    # SMTP Email Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TIMEOUT: float = 10.0
    EMAIL_FROM: str = "noreply@ai-powered-assistance-platform.com"

    # Email Token Settings
    EMAIL_VERIFICATION_EXPIRY_HOURS: int = 24
    PASSWORD_RESET_EXPIRY_MINUTES: int = 15

    # Adzuna Job API
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    ADZUNA_API_KEY: str = ""

    # Rate Limiting & Logging
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_STORAGE_URL: Optional[str] = None
    TRUST_PROXY_HEADERS: bool = False
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"
    LOG_LEVEL: str = "INFO"

    @property
    def is_production(self) -> bool:
        return (self.ENVIRONMENT or "").lower() in {"production", "prod"}

    @property
    def is_development(self) -> bool:
        env = (self.ENVIRONMENT or "").lower()
        if os.environ.get("TESTING") == "true" or env in {"test", "testing"}:
            return True
        return env in {"development", "dev"} and bool(self.DEBUG)

    if IS_PYDANTIC_V2:
        @field_validator("DEBUG", mode="before")
        @classmethod
        def parse_debug_v2(cls, value):
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "y", "on", "t"}:
                    return True
                if normalized in {"0", "false", "no", "n", "off", "f", "release", "prod", "production"}:
                    return False
            return value

        @field_validator("LLM_PROVIDER", mode="before")
        @classmethod
        def normalize_llm_provider_v2(cls, value):
            return "ollama"

        @field_validator("CORS_ORIGINS", mode="before")
        @classmethod
        def normalize_cors_origins_v2(cls, value):
            entries = []
            if value:
                entries.extend(str(value).split(","))
            entries.extend(DEFAULT_CORS_ORIGINS)
            cleaned = []
            seen = set()
            for entry in entries:
                cleaned_entry = entry.strip().rstrip("/")
                if not cleaned_entry or cleaned_entry in seen:
                    continue
                cleaned.append(cleaned_entry)
                seen.add(cleaned_entry)
            return ",".join(cleaned)

        @model_validator(mode="after")
        def validate_and_resolve_paths_v2(self):
            # Resolve relative storage paths deterministically
            self.CHROMA_PATH = resolve_app_path(self.CHROMA_PATH)
            self.UPLOAD_DIR = resolve_app_path(self.UPLOAD_DIR)
            self.LLM_PROVIDER = "ollama"

            # Resolve SQLite database path if relative
            if self.DATABASE_URL.startswith("sqlite:///") and not self.DATABASE_URL.startswith("sqlite:///:memory:"):
                raw_path = self.DATABASE_URL.replace("sqlite:///", "", 1)
                if not Path(raw_path).is_absolute():
                    resolved_db = resolve_app_path(raw_path)
                    self.DATABASE_URL = f"sqlite:///{resolved_db}"

            # Security validations for non-development / non-test and production environments
            env = getattr(self, "ENVIRONMENT", "").lower()
            if env not in {"development", "dev", "test", "testing"}:
                key = getattr(self, "SECRET_KEY", "")
                if not key or len(key) < 32:
                    raise ValueError(f"SECRET_KEY must be set and at least 32 characters long in {env or 'non-development'} environment.")
                forbidden_substrings = [
                    "test", "secret", "changeme", "dev", "example", "default",
                    "your-super-secret-jwt-key", "your-secret-key", "replace-with-secure"
                ]
                if any(sub in key.lower() for sub in forbidden_substrings):
                    raise ValueError(f"SECRET_KEY contains insecure placeholder substring in {env or 'non-development'} environment.")

            if env in {"production", "prod"}:
                db_url = getattr(self, "DATABASE_URL", "")
                if not db_url:
                    raise ValueError("DATABASE_URL must be configured in production environment.")
                if "sqlite" in db_url.lower():
                    raise ValueError("SQLite is not supported in production environment. A valid PostgreSQL connection string (DATABASE_URL) is required.")
                if "localhost:5432/ai_platform_db" in db_url or "USER:PASSWORD" in db_url:
                    raise ValueError("DATABASE_URL contains default/placeholder credentials in production environment.")
            return self
    else:
        @validator("DEBUG", pre=True)
        def parse_debug_v1(cls, value):
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "y", "on", "t"}:
                    return True
                if normalized in {"0", "false", "no", "n", "off", "f", "release", "prod", "production"}:
                    return False
            return value

        @validator("LLM_PROVIDER", pre=True)
        def normalize_llm_provider_v1(cls, value):
            return "ollama"

        @validator("CORS_ORIGINS", pre=True)
        def normalize_cors_origins_v1(cls, value):
            entries = []
            if value:
                entries.extend(str(value).split(","))
            entries.extend(DEFAULT_CORS_ORIGINS)
            cleaned = []
            seen = set()
            for entry in entries:
                cleaned_entry = entry.strip().rstrip("/")
                if not cleaned_entry or cleaned_entry in seen:
                    continue
                cleaned.append(cleaned_entry)
                seen.add(cleaned_entry)
            return ",".join(cleaned)

        @root_validator
        def validate_and_resolve_paths_v1(cls, values):
            chroma = values.get("CHROMA_PATH", "./data/chroma_db")
            values["CHROMA_PATH"] = resolve_app_path(chroma)
            upload = values.get("UPLOAD_DIR", "./uploads")
            values["UPLOAD_DIR"] = resolve_app_path(upload)
            values["LLM_PROVIDER"] = "ollama"

            db_url = values.get("DATABASE_URL", "")
            if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
                raw_path = db_url.replace("sqlite:///", "", 1)
                if not Path(raw_path).is_absolute():
                    resolved_db = resolve_app_path(raw_path)
                    values["DATABASE_URL"] = f"sqlite:///{resolved_db}"

            env = (values.get("ENVIRONMENT") or "").lower()
            if env not in {"development", "dev", "test", "testing"}:
                key = values.get("SECRET_KEY") or ""
                if not key or len(key) < 32:
                    raise ValueError(f"SECRET_KEY must be set and at least 32 characters long in {env or 'non-development'} environment.")
                forbidden_substrings = [
                    "test", "secret", "changeme", "dev", "example", "default",
                    "your-super-secret-jwt-key", "your-secret-key", "replace-with-secure"
                ]
                if any(sub in key.lower() for sub in forbidden_substrings):
                    raise ValueError(f"SECRET_KEY contains insecure placeholder substring in {env or 'non-development'} environment.")

            if env in {"production", "prod"}:
                if not db_url:
                    raise ValueError("DATABASE_URL must be configured in production environment.")
                if "sqlite" in db_url.lower():
                    raise ValueError("SQLite is not supported in production environment. A valid PostgreSQL connection string (DATABASE_URL) is required.")
                if "localhost:5432/ai_platform_db" in db_url or "USER:PASSWORD" in db_url:
                    raise ValueError("DATABASE_URL contains default/placeholder credentials in production environment.")
            return values

    if IS_PYDANTIC_V2 and SettingsConfigDict:
        _env_candidates = []
        if (PROJECT_ROOT / ".env").is_file():
            _env_candidates.append(str(PROJECT_ROOT / ".env"))
        if (BACKEND_DIR / ".env").is_file() and str(BACKEND_DIR / ".env") not in _env_candidates:
            _env_candidates.append(str(BACKEND_DIR / ".env"))

        model_config = SettingsConfigDict(
            env_file=tuple(_env_candidates) if _env_candidates else None,
            env_file_encoding="utf-8",
            extra="ignore"
        )
    else:
        class Config:
            env_file = str(PROJECT_ROOT / ".env") if (PROJECT_ROOT / ".env").is_file() else (
                str(BACKEND_DIR / ".env") if (BACKEND_DIR / ".env").is_file() else None
            )
            env_file_encoding = "utf-8"
            extra = "ignore"


settings = Settings()


def ensure_storage_directories():
    """Ensure persistent storage and upload directories exist without crashing at import time."""
    for d in [settings.UPLOAD_DIR, settings.CHROMA_PATH]:
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create storage directory '{d}': {e}")
    if settings.DATABASE_URL.startswith("sqlite:///") and not settings.DATABASE_URL.startswith("sqlite:///:memory:"):
        db_file = settings.DATABASE_URL.replace("sqlite:///", "", 1)
        try:
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


# Safely ensure directories upon module load
ensure_storage_directories()
