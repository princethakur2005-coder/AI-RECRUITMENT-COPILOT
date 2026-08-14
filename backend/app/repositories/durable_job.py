from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.durable_job import CLAIMABLE_JOB_STATUSES, DurableJobStatus
from app.models.durable_job import DurableJob
from app.repositories.base import BaseRepository


class DurableJobRepository(BaseRepository[DurableJob]):
    """Persistence for PostgreSQL-backed durable jobs."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, DurableJob)

    def get_by_idempotency_key(self, idempotency_key: str) -> DurableJob | None:
        if not idempotency_key:
            return None
        statement = select(DurableJob).where(DurableJob.idempotency_key == idempotency_key)
        return self.db.scalar(statement)

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_types: list[str] | None = None,
    ) -> DurableJob | None:
        """Atomically claim one runnable job (FOR UPDATE SKIP LOCKED on PostgreSQL)."""
        claimable = [status.value for status in CLAIMABLE_JOB_STATUSES]
        statement = (
            select(DurableJob)
            .where(
                DurableJob.status.in_(claimable),
                or_(DurableJob.scheduled_at.is_(None), DurableJob.scheduled_at <= now),
                or_(DurableJob.next_run_at.is_(None), DurableJob.next_run_at <= now),
            )
            .order_by(DurableJob.priority.desc(), DurableJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_types:
            statement = statement.where(DurableJob.job_type.in_(job_types))

        job = self.db.scalars(statement).first()
        if job is None:
            return None

        updates: dict[str, object] = {
            "status": DurableJobStatus.RUNNING.value,
            "locked_at": now,
            "locked_by": worker_id,
            "updated_at": now,
        }
        if job.started_at is None:
            updates["started_at"] = now
        return self.update(job, updates, commit=False)

    def recover_stale_running(
        self,
        *,
        now: datetime,
        stale_before: datetime,
    ) -> list[DurableJob]:
        """Return abandoned RUNNING jobs to retryable state for worker recovery."""
        statement = select(DurableJob).where(
            DurableJob.status == DurableJobStatus.RUNNING.value,
            DurableJob.locked_at.is_not(None),
            DurableJob.locked_at < stale_before,
        )
        stale_jobs = list(self.db.scalars(statement).all())
        recovered: list[DurableJob] = []
        for job in stale_jobs:
            attempt = job.attempt_count + 1
            if attempt >= job.max_attempts:
                recovered.append(
                    self.update(
                        job,
                        {
                            "status": DurableJobStatus.FAILED_PERMANENT.value,
                            "attempt_count": attempt,
                            "completed_at": now,
                            "locked_at": None,
                            "locked_by": None,
                            "error_code": "stale_running",
                            "error_message": "Job abandoned in running state",
                            "updated_at": now,
                        },
                        commit=False,
                    )
                )
            else:
                recovered.append(
                    self.update(
                        job,
                        {
                            "status": DurableJobStatus.FAILED_RETRYABLE.value,
                            "attempt_count": attempt,
                            "next_run_at": now,
                            "locked_at": None,
                            "locked_by": None,
                            "error_code": "stale_running",
                            "error_message": "Job recovered from stale running state",
                            "updated_at": now,
                        },
                        commit=False,
                    )
                )
        return recovered

    def submit_idempotent(
        self,
        job: DurableJob,
        *,
        commit: bool = True,
    ) -> tuple[DurableJob, bool]:
        """Insert job; on idempotency conflict return existing row (created=False)."""
        try:
            created = self.create(job, commit=commit)
            return created, True
        except IntegrityError:
            self.db.rollback()
            if job.idempotency_key:
                existing = self.get_by_idempotency_key(job.idempotency_key)
                if existing is not None:
                    return existing, False
            raise
