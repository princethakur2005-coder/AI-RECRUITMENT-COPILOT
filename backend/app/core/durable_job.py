"""Durable background job contracts — explicit lifecycle and job types."""

from __future__ import annotations

from enum import StrEnum


class DurableJobStatus(StrEnum):
    """Production job lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES: frozenset[DurableJobStatus] = frozenset(
    {
        DurableJobStatus.SUCCEEDED,
        DurableJobStatus.FAILED_PERMANENT,
        DurableJobStatus.CANCELLED,
    }
)

CLAIMABLE_JOB_STATUSES: frozenset[DurableJobStatus] = frozenset(
    {
        DurableJobStatus.PENDING,
        DurableJobStatus.FAILED_RETRYABLE,
    }
)


class DurableJobType(StrEnum):
    """Registered durable job types. Extend as new workers are added."""

    EMAIL_DELIVERY = "email.delivery"
    WEBHOOK_DELIVERY = "webhook.delivery"
    CALENDAR_SYNC = "calendar.sync"
    RESUME_INTELLIGENCE = "resume.intelligence"



ALLOWED_JOB_TRANSITIONS: dict[DurableJobStatus, frozenset[DurableJobStatus]] = {
    DurableJobStatus.PENDING: frozenset(
        {DurableJobStatus.RUNNING, DurableJobStatus.CANCELLED}
    ),
    DurableJobStatus.RUNNING: frozenset(
        {
            DurableJobStatus.SUCCEEDED,
            DurableJobStatus.FAILED_RETRYABLE,
            DurableJobStatus.FAILED_PERMANENT,
            DurableJobStatus.CANCELLED,
            # Stale recovery may return abandoned jobs to retryable/pending.
            DurableJobStatus.PENDING,
        }
    ),
    DurableJobStatus.FAILED_RETRYABLE: frozenset(
        {DurableJobStatus.PENDING, DurableJobStatus.RUNNING, DurableJobStatus.CANCELLED}
    ),
    DurableJobStatus.SUCCEEDED: frozenset(),
    DurableJobStatus.FAILED_PERMANENT: frozenset(),
    DurableJobStatus.CANCELLED: frozenset(),
}


def validate_job_transition(current: DurableJobStatus, new: DurableJobStatus) -> DurableJobStatus:
    if current == new:
        return current
    allowed = ALLOWED_JOB_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValueError(f"Invalid durable job transition from '{current}' to '{new}'")
    return new


class JobExecutionError(Exception):
    """Raised by job handlers to signal retryable or permanent failure."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.error_code = error_code


_SENSITIVE_ERROR_MARKERS = (
    "password",
    "secret",
    "token",
    "jwt",
    "authorization",
    "credentials",
    "postgresql",
    "smtp",
    "api_key",
    "bearer",
)


def sanitize_job_error_message(message: str | None, *, max_length: int = 2000) -> str | None:
    """Redact sensitive fragments before persisting or returning job errors."""
    if message is None:
        return None
    trimmed = str(message).strip()
    if not trimmed:
        return None
    trimmed = trimmed[:max_length]
    lowered = trimmed.lower()
    if any(marker in lowered for marker in _SENSITIVE_ERROR_MARKERS):
        return "Job execution failed"
    return trimmed
