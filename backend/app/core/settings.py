from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List

from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Recruitment Copilot API"
    API_VERSION: str = "0.1.0"
    SECRET_KEY: str
    DATABASE_URL: str
    DEBUG: bool = False
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver", "backend"]
    CORS_ORIGINS: List[str] = ["http://localhost", "http://127.0.0.1"]
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

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    REDIS_PREFIX: str = "airc"
    REDIS_CONNECT_TIMEOUT_SECONDS: int = 3
    REDIS_SOCKET_TIMEOUT_SECONDS: int = 3
    REDIS_HEALTHCHECK_TIMEOUT_SECONDS: int = 2

    CACHE_DEFAULT_TTL_SECONDS: int = 600
    CACHE_MAX_LOCAL_ENTRIES: int = 2048

    JOB_QUEUE_PREFIX: str = "jobs"
    DISTRIBUTED_LOCK_PREFIX: str = "locks"
    SESSION_CACHE_PREFIX: str = "sessions"
    CACHE_INVALIDATION_PREFIX: str = "invalidation"
    # Resilience & error handling
    DEFAULT_REQUEST_TIMEOUT_SECONDS: int = 15
    EXTERNAL_SERVICE_TIMEOUT_SECONDS: int = 10
    EXTERNAL_SERVICE_RETRY_ATTEMPTS: int = 3
    EXTERNAL_SERVICE_RETRY_BACKOFF_FACTOR: float = 0.5
    RESILIENCE_GRACEFUL_DEGRADATION_ENABLED: bool = True
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

    @property
    def is_debug(self) -> bool:
        return self.DEBUG

    @property
    def is_production(self) -> bool:
        return not self.DEBUG

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
