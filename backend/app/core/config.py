import json
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator, root_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from the backend environment file."""

    @field_validator("ALLOWED_HOSTS", "CORS_ORIGINS", mode="before")
    @classmethod
    def parse_string_lists(cls, value):
        if value is None:
            return value

        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []

            if stripped_value.startswith("[") and stripped_value.endswith("]"):
                try:
                    parsed = json.loads(stripped_value)
                except json.JSONDecodeError:
                    normalized = stripped_value.replace("'", '"')
                    try:
                        parsed = json.loads(normalized)
                    except json.JSONDecodeError:
                        parsed = [item.strip().strip("'\"") for item in stripped_value[1:-1].split(",") if item.strip()]
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]

            if "," in stripped_value:
                return [item.strip().strip("'\"") for item in stripped_value.split(",") if item.strip()]

            return [stripped_value.strip().strip("'\"")]

        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]

        return value

    PROJECT_NAME: str = "AI Recruitment Copilot API"
    API_VERSION: str = "0.1.0"
    SECRET_KEY: str = Field(default="change-me-in-production", env="SECRET_KEY")
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/ai_recruitment_copilot",
        env="DATABASE_URL",
    )
    DEBUG: bool = True
    ALLOWED_HOSTS: List[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "backend"],
        env="ALLOWED_HOSTS",
    )
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost", "http://127.0.0.1"], env="CORS_ORIGINS")
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    MAX_REQUEST_SIZE: int = 10 * 1024 * 1024

    # Security hardening
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_COOKIE_SECURE: bool = True
    CSRF_COOKIE_SAMESITE: str = "Lax"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    CSRF_ENABLED: bool = True
    CONTENT_SECURITY_POLICY: str = Field(
        default=(
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        ),
        env="CONTENT_SECURITY_POLICY",
    )
    CSP_ENABLED: bool = True
    REFERRER_POLICY: str = "no-referrer"
    PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=()"
    X_CONTENT_TYPE_OPTIONS: str = "nosniff"
    X_FRAME_OPTIONS: str = "DENY"
    X_XSS_PROTECTION: str = "0"
    STRICT_TRANSPORT_SECURITY: str = Field(
        default="max-age=31536000; includeSubDomains; preload",
        env="STRICT_TRANSPORT_SECURITY",
    )
    HSTS_ENABLED: bool = True
    HSTS_MAX_AGE: int = 31536000
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = True

    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_AUDIENCE: str = "ai-recruitment-copilot-users"
    JWT_ISSUER: str = "ai-recruitment-copilot"
    JWT_LEEWAY_SECONDS: int = 10
    MAX_JWT_TOKEN_LENGTH: int = 2000

    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # Redis & cache settings (used by cache service)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    REDIS_PREFIX: str = "airc"
    REDIS_CONNECT_TIMEOUT_SECONDS: int = 3
    REDIS_SOCKET_TIMEOUT_SECONDS: int = 3
    REDIS_HEALTHCHECK_TIMEOUT_SECONDS: int = 2

    CACHE_DEFAULT_TTL_SECONDS: int = 600
    CACHE_MAX_LOCAL_ENTRIES: int = 2048
    # In-process read cache for reporting aggregates only. Not Redis.
    READ_CACHE_ENABLED: bool = Field(default=True, env="READ_CACHE_ENABLED")
    READ_CACHE_MAX_ENTRIES: int = Field(default=2048, env="READ_CACHE_MAX_ENTRIES")
    REPORTING_CACHE_TTL_SECONDS: int = Field(default=30, env="REPORTING_CACHE_TTL_SECONDS")
    DASHBOARD_CACHE_TTL_SECONDS: int = Field(default=30, env="DASHBOARD_CACHE_TTL_SECONDS")

    JOB_QUEUE_PREFIX: str = "jobs"
    DISTRIBUTED_LOCK_PREFIX: str = "locks"
    SESSION_CACHE_PREFIX: str = "sessions"
    CACHE_INVALIDATION_PREFIX: str = "invalidation"

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    LOG_ROTATION_ENABLED: bool = False
    LOG_FILE_PATH: str = "/tmp/ai-recruitment-api.log"
    LOG_ROTATION_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_ROTATION_BACKUP_COUNT: int = 5

    REQUEST_ID_HEADER_NAME: str = "X-Request-ID"
    METRICS_ENABLED: bool = True
    HEALTHCHECK_ENABLE_DEPENDENCIES: bool = False
    # Resilience & error handling
    DEFAULT_REQUEST_TIMEOUT_SECONDS: int = 15
    EXTERNAL_SERVICE_TIMEOUT_SECONDS: int = 10
    EXTERNAL_SERVICE_RETRY_ATTEMPTS: int = 3
    EXTERNAL_SERVICE_RETRY_BACKOFF_FACTOR: float = 0.5
    RESILIENCE_GRACEFUL_DEGRADATION_ENABLED: bool = False
    ERROR_VERBOSITY: str = "minimal"  # one of: minimal, normal, verbose
    # Performance tuning
    COMPRESS_MIN_SIZE: int = 500
    CACHE_CONTROL_DEFAULT_TTL: int = 60
    SLOW_REQUEST_THRESHOLD_MS: int = 500
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    BACKGROUND_WORKER_THREADS: int = 4
    MEMORY_LIMIT_MB: int = 0
    GC_COLLECT_INTERVAL_SECONDS: int = 300

    # Email delivery (transport). Credentials from env — never hard-code secrets.
    EMAIL_DELIVERY_ENABLED: bool = Field(default=False, env="EMAIL_DELIVERY_ENABLED")
    SMTP_HOST: str | None = Field(default=None, env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USERNAME: str | None = Field(default=None, env="SMTP_USERNAME")
    SMTP_USER: str | None = Field(default=None, env="SMTP_USER")  # legacy alias source
    SMTP_PASSWORD: str | None = Field(default=None, env="SMTP_PASSWORD")
    SMTP_USE_TLS: bool = Field(default=True, env="SMTP_USE_TLS")
    SMTP_FROM_EMAIL: str | None = Field(default=None, env="SMTP_FROM_EMAIL")
    SMTP_FROM: str | None = Field(default=None, env="SMTP_FROM")  # legacy alias source
    SMTP_FROM_NAME: str | None = Field(default="AI Recruitment Copilot", env="SMTP_FROM_NAME")
    SMTP_REPLY_TO: str | None = Field(default=None, env="SMTP_REPLY_TO")
    SMTP_TIMEOUT_SECONDS: int = Field(default=10, env="SMTP_TIMEOUT_SECONDS")

    # Durable background jobs (PostgreSQL source of truth).
    DURABLE_JOB_DEFAULT_MAX_ATTEMPTS: int = Field(default=5, env="DURABLE_JOB_DEFAULT_MAX_ATTEMPTS")
    DURABLE_JOB_RETRY_BASE_SECONDS: int = Field(default=30, env="DURABLE_JOB_RETRY_BASE_SECONDS")
    DURABLE_JOB_RETRY_MAX_SECONDS: int = Field(default=3600, env="DURABLE_JOB_RETRY_MAX_SECONDS")
    DURABLE_JOB_STALE_RUNNING_SECONDS: int = Field(default=300, env="DURABLE_JOB_STALE_RUNNING_SECONDS")
    DURABLE_JOB_WORKER_BATCH_SIZE: int = Field(default=10, env="DURABLE_JOB_WORKER_BATCH_SIZE")
    DURABLE_JOB_WORKER_POLL_SECONDS: float = Field(default=2.0, env="DURABLE_JOB_WORKER_POLL_SECONDS")

    # Outbound webhooks (HTTP delivery via durable jobs).
    WEBHOOK_HTTP_TIMEOUT_SECONDS: float = Field(default=10.0, env="WEBHOOK_HTTP_TIMEOUT_SECONDS")
    WEBHOOK_ALLOW_HTTP_LOCALHOST: bool = Field(default=True, env="WEBHOOK_ALLOW_HTTP_LOCALHOST")
    WEBHOOK_VALIDATE_DNS: bool = Field(default=True, env="WEBHOOK_VALIDATE_DNS")
    WEBHOOK_SKIP_DNS_VALIDATION: bool = Field(default=False, env="WEBHOOK_SKIP_DNS_VALIDATION")

    @property
    def smtp_username_effective(self) -> str | None:
        return (self.SMTP_USERNAME or self.SMTP_USER or None)

    @property
    def smtp_from_email_effective(self) -> str | None:
        return (self.SMTP_FROM_EMAIL or self.SMTP_FROM or None)

    @property
    def is_debug(self) -> bool:
        return self.DEBUG

    @property
    def is_production(self) -> bool:
        return not self.DEBUG

    @root_validator(skip_on_failure=True)
    def validate_production_settings(cls, values):
        debug = values.get("DEBUG")
        secret = values.get("SECRET_KEY")
        database_url = values.get("DATABASE_URL")
        allowed_hosts = values.get("ALLOWED_HOSTS")
        cors_origins = values.get("CORS_ORIGINS")
        hsts_enabled = values.get("HSTS_ENABLED")
        jwt_audience = values.get("JWT_AUDIENCE")
        jwt_issuer = values.get("JWT_ISSUER")
        email_enabled = values.get("EMAIL_DELIVERY_ENABLED")
        smtp_host = values.get("SMTP_HOST")
        smtp_from_email = values.get("SMTP_FROM_EMAIL") or values.get("SMTP_FROM")
        webhook_allow_localhost = values.get("WEBHOOK_ALLOW_HTTP_LOCALHOST")
        webhook_skip_dns = values.get("WEBHOOK_SKIP_DNS_VALIDATION")
        poll_seconds = values.get("DURABLE_JOB_WORKER_POLL_SECONDS")
        batch_size = values.get("DURABLE_JOB_WORKER_BATCH_SIZE")
        error_verbosity = values.get("ERROR_VERBOSITY")

        if poll_seconds is not None and float(poll_seconds) <= 0:
            raise ValueError("DURABLE_JOB_WORKER_POLL_SECONDS must be greater than zero.")
        if batch_size is not None and int(batch_size) <= 0:
            raise ValueError("DURABLE_JOB_WORKER_BATCH_SIZE must be greater than zero.")

        if not debug:
            if not secret or secret == "change-me-in-production":
                raise ValueError("SECRET_KEY must be configured for production deployments.")
            if not database_url or database_url == "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_recruitment_copilot":
                raise ValueError("DATABASE_URL must be configured for production deployments.")
            if database_url.startswith("sqlite"):
                raise ValueError("SQLite DATABASE_URL must not be used in production deployments.")
            if not allowed_hosts:
                raise ValueError("ALLOWED_HOSTS must contain at least one host in production.")
            if not cors_origins:
                raise ValueError("CORS_ORIGINS must contain at least one allowed origin in production.")
            if hsts_enabled and not values.get("STRICT_TRANSPORT_SECURITY"):
                raise ValueError("STRICT_TRANSPORT_SECURITY must be configured when HSTS is enabled in production.")
            if not jwt_audience:
                raise ValueError("JWT_AUDIENCE must be configured for production deployments.")
            if not jwt_issuer:
                raise ValueError("JWT_ISSUER must be configured for production deployments.")
            if email_enabled and (not smtp_host or not smtp_from_email):
                raise ValueError(
                    "EMAIL_DELIVERY_ENABLED requires SMTP_HOST and SMTP_FROM_EMAIL in production deployments."
                )
            if webhook_allow_localhost:
                raise ValueError("WEBHOOK_ALLOW_HTTP_LOCALHOST must be false in production deployments.")
            if webhook_skip_dns:
                raise ValueError("WEBHOOK_SKIP_DNS_VALIDATION must be false in production deployments.")
            if error_verbosity == "verbose":
                raise ValueError("ERROR_VERBOSITY must not be 'verbose' in production deployments.")

        return values

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance for the application."""
    return Settings()


settings = get_settings()
