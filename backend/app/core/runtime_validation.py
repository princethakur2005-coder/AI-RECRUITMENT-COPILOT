from __future__ import annotations

from app.core.config import Settings


def validate_worker_runtime(settings: Settings) -> None:
    """Validate durable worker configuration before the worker loop starts."""
    if settings.DURABLE_JOB_WORKER_POLL_SECONDS <= 0:
        raise ValueError("DURABLE_JOB_WORKER_POLL_SECONDS must be greater than zero.")
    if settings.DURABLE_JOB_WORKER_BATCH_SIZE <= 0:
        raise ValueError("DURABLE_JOB_WORKER_BATCH_SIZE must be greater than zero.")
    if settings.DURABLE_JOB_DEFAULT_MAX_ATTEMPTS <= 0:
        raise ValueError("DURABLE_JOB_DEFAULT_MAX_ATTEMPTS must be greater than zero.")
    if settings.DURABLE_JOB_STALE_RUNNING_SECONDS <= 0:
        raise ValueError("DURABLE_JOB_STALE_RUNNING_SECONDS must be greater than zero.")
    if settings.DURABLE_JOB_RETRY_BASE_SECONDS <= 0:
        raise ValueError("DURABLE_JOB_RETRY_BASE_SECONDS must be greater than zero.")
    if settings.DURABLE_JOB_RETRY_MAX_SECONDS <= 0:
        raise ValueError("DURABLE_JOB_RETRY_MAX_SECONDS must be greater than zero.")


def validate_api_runtime(settings: Settings) -> None:
    """Validate API process configuration at startup."""
    validate_worker_runtime(settings)

    if settings.is_production:
        if settings.SECRET_KEY == "change-me-in-production":
            raise ValueError("SECRET_KEY must be configured for production API deployments.")
        if settings.DATABASE_URL.startswith("sqlite"):
            raise ValueError("SQLite DATABASE_URL must not be used in production API deployments.")
        if settings.ERROR_VERBOSITY == "verbose":
            raise ValueError("ERROR_VERBOSITY must not be 'verbose' in production API deployments.")
        if settings.EMAIL_DELIVERY_ENABLED and (
            not settings.SMTP_HOST or not settings.smtp_from_email_effective
        ):
            raise ValueError(
                "EMAIL_DELIVERY_ENABLED requires SMTP_HOST and SMTP_FROM_EMAIL in production API deployments."
            )
        if settings.WEBHOOK_ALLOW_HTTP_LOCALHOST:
            raise ValueError("WEBHOOK_ALLOW_HTTP_LOCALHOST must be false in production API deployments.")
        if settings.WEBHOOK_SKIP_DNS_VALIDATION:
            raise ValueError("WEBHOOK_SKIP_DNS_VALIDATION must be false in production API deployments.")
