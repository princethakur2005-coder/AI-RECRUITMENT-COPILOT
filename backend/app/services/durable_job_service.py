"""Durable job submission, lifecycle, and handler dispatch."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.durable_job import (
    DurableJobStatus,
    DurableJobType,
    JobExecutionError,
    TERMINAL_JOB_STATUSES,
    sanitize_job_error_message,
    validate_job_transition,
)
from app.models.durable_job import DurableJob
from app.repositories.durable_job import DurableJobRepository
from app.schemas.durable_job import DurableJobResponse, DurableJobSubmit

logger = logging.getLogger("app.durable_job")

JobHandler = Callable[[DurableJob], None]


class DurableJobService:
    """Application boundary for durable background job orchestration."""

    def __init__(
        self,
        repository: DurableJobRepository,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self._handlers: dict[str, JobHandler] = {}

    def register_handler(self, job_type: str | DurableJobType, handler: JobHandler) -> None:
        key = job_type.value if isinstance(job_type, DurableJobType) else str(job_type)
        self._handlers[key] = handler

    def submit(self, payload: DurableJobSubmit) -> DurableJobResponse:
        job_type = (
            payload.job_type.value
            if isinstance(payload.job_type, DurableJobType)
            else str(payload.job_type)
        )
        now = datetime.now(timezone.utc)
        max_attempts = payload.max_attempts or self.settings.DURABLE_JOB_DEFAULT_MAX_ATTEMPTS

        if payload.idempotency_key:
            existing = self.repository.get_by_idempotency_key(payload.idempotency_key)
            if existing is not None:
                return DurableJobResponse.from_orm_job(existing)

        job = DurableJob(
            job_type=job_type,
            status=DurableJobStatus.PENDING.value,
            payload_json=dict(payload.payload or {}),
            attempt_count=0,
            max_attempts=max_attempts,
            priority=payload.priority,
            scheduled_at=payload.scheduled_at,
            next_run_at=payload.scheduled_at,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
            company_id=payload.company_id,
        )
        created, _ = self.repository.submit_idempotent(job)
        return DurableJobResponse.from_orm_job(created)

    def get(self, job_id: UUID) -> DurableJobResponse | None:
        row = self.repository.get_by_id(job_id)
        if row is None:
            return None
        return DurableJobResponse.from_orm_job(row)

    def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
    ) -> DurableJob | None:
        now = datetime.now(timezone.utc)
        self.recover_stale_jobs(now=now)
        return self.repository.claim_next(worker_id=worker_id, now=now, job_types=job_types)

    def execute_claimed(self, job: DurableJob) -> DurableJobResponse:
        current_status = DurableJobStatus(job.status)
        if current_status != DurableJobStatus.RUNNING:
            logger.warning(
                "durable_job_execute_skipped job_id=%s status=%s",
                job.id,
                job.status,
            )
            return DurableJobResponse.from_orm_job(job)

        handler = self._handlers.get(job.job_type)
        if handler is None:
            return self._finalize_permanent_failure(
                job,
                error_code="unknown_job_type",
                error_message=f"No handler registered for job type '{job.job_type}'",
            )

        try:
            handler(job)
            return self._finalize_success(job)
        except JobExecutionError as exc:
            safe_message = sanitize_job_error_message(str(exc)) or "Job execution failed"
            if exc.retryable:
                return self._finalize_retryable_failure(
                    job,
                    error_code=exc.error_code or "job_failed",
                    error_message=safe_message,
                )
            return self._finalize_permanent_failure(
                job,
                error_code=exc.error_code or "job_failed_permanent",
                error_message=safe_message,
            )
        except Exception as exc:
            logger.error(
                "durable_job_handler_error job_id=%s job_type=%s error_type=%s",
                job.id,
                job.job_type,
                type(exc).__name__,
            )
            return self._finalize_retryable_failure(
                job,
                error_code=type(exc).__name__,
                error_message=sanitize_job_error_message(str(exc)) or "Job execution failed",
            )

    def recover_stale_jobs(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        stale_seconds = int(self.settings.DURABLE_JOB_STALE_RUNNING_SECONDS)
        stale_before = now - timedelta(seconds=stale_seconds)
        recovered = self.repository.recover_stale_running(now=now, stale_before=stale_before)
        if recovered:
            self.repository.db.commit()
            logger.info("durable_jobs_recovered_stale count=%s", len(recovered))
        return len(recovered)

    def cancel(self, job_id: UUID, reason: str | None = None) -> DurableJobResponse | None:
        job = self.repository.get_by_id(job_id)
        if job is None:
            return None
        if DurableJobStatus(job.status) in TERMINAL_JOB_STATUSES:
            return DurableJobResponse.from_orm_job(job)
        now = datetime.now(timezone.utc)
        updated = self.repository.update(
            job,
            {
                "status": DurableJobStatus.CANCELLED.value,
                "completed_at": now,
                "locked_at": None,
                "locked_by": None,
                "error_message": reason,
                "updated_at": now,
            },
        )
        return DurableJobResponse.from_orm_job(updated)

    def _finalize_success(self, job: DurableJob) -> DurableJobResponse:
        now = datetime.now(timezone.utc)
        validate_job_transition(DurableJobStatus(job.status), DurableJobStatus.SUCCEEDED)
        updated = self.repository.update(
            job,
            {
                "status": DurableJobStatus.SUCCEEDED.value,
                "completed_at": now,
                "locked_at": None,
                "locked_by": None,
                "error_code": None,
                "error_message": None,
                "updated_at": now,
            },
        )
        return DurableJobResponse.from_orm_job(updated)

    def _finalize_retryable_failure(
        self,
        job: DurableJob,
        *,
        error_code: str,
        error_message: str,
    ) -> DurableJobResponse:
        now = datetime.now(timezone.utc)
        attempt = job.attempt_count + 1
        if attempt >= job.max_attempts:
            return self._finalize_permanent_failure(
                job,
                error_code=error_code,
                error_message=error_message,
                attempt_count=attempt,
            )

        next_run = self._compute_next_run_at(attempt, now)
        validate_job_transition(DurableJobStatus(job.status), DurableJobStatus.FAILED_RETRYABLE)
        error_message = sanitize_job_error_message(error_message) or "Job execution failed"
        updated = self.repository.update(
            job,
            {
                "status": DurableJobStatus.FAILED_RETRYABLE.value,
                "attempt_count": attempt,
                "next_run_at": next_run,
                "locked_at": None,
                "locked_by": None,
                "error_code": error_code,
                "error_message": error_message,
                "updated_at": now,
            },
        )
        return DurableJobResponse.from_orm_job(updated)

    def _finalize_permanent_failure(
        self,
        job: DurableJob,
        *,
        error_code: str,
        error_message: str,
        attempt_count: int | None = None,
    ) -> DurableJobResponse:
        now = datetime.now(timezone.utc)
        validate_job_transition(DurableJobStatus(job.status), DurableJobStatus.FAILED_PERMANENT)
        error_message = sanitize_job_error_message(error_message) or "Job execution failed"
        updated = self.repository.update(
            job,
            {
                "status": DurableJobStatus.FAILED_PERMANENT.value,
                "attempt_count": attempt_count if attempt_count is not None else job.attempt_count + 1,
                "completed_at": now,
                "locked_at": None,
                "locked_by": None,
                "error_code": error_code,
                "error_message": error_message,
                "updated_at": now,
            },
        )
        return DurableJobResponse.from_orm_job(updated)

    def _compute_next_run_at(self, attempt_count: int, now: datetime) -> datetime:
        base = float(self.settings.DURABLE_JOB_RETRY_BASE_SECONDS)
        max_delay = float(self.settings.DURABLE_JOB_RETRY_MAX_SECONDS)
        delay = min(max_delay, base * math.pow(2, max(attempt_count - 1, 0)))
        return now + timedelta(seconds=delay)
