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


def validate_api_runtime(settings: Settings) -> None:
    """Validate API process configuration at startup."""
    validate_worker_runtime(settings)
