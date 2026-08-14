"""Legacy in-memory job metadata — superseded by PostgreSQL DurableJobService.

Production background processing uses ``app.services.durable_job_service.DurableJobService``
with ``app.services.durable_job_worker.DurableJobWorker``.

This module remains for backward-compatible metadata APIs only; do not use for
email delivery or other externally visible side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.services.cache import background_job_queue
from app.schemas.background_job import (
    BackgroundJobCreate,
    BackgroundJobExecutionEvent,
    BackgroundJobFilter,
    BackgroundJobListResponse,
    BackgroundJobPriority,
    BackgroundJobResponse,
    BackgroundJobStatus,
)


class BackgroundJobService:
    """In-process metadata scheduler (non-durable). Use DurableJobService in production."""

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._items: dict[UUID, BackgroundJobResponse] = {}
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._queue = background_job_queue

    def schedule_job(self, payload: BackgroundJobCreate) -> BackgroundJobResponse:
        now = self._now_provider()
        scheduled_at = payload.scheduled_at or now

        status = BackgroundJobStatus.SCHEDULED
        if scheduled_at <= now:
            status = BackgroundJobStatus.QUEUED

        job = BackgroundJobResponse(
            id=uuid4(),
            job_type=payload.job_type,
            payload=dict(payload.payload or {}),
            status=status,
            priority=payload.priority,
            retry=payload.retry,
            scheduled_at=scheduled_at,
            metadata=dict(payload.metadata or {}),
            execution_history=[
                BackgroundJobExecutionEvent(
                    event="scheduled",
                    timestamp=now,
                    details={
                        "status": status.value,
                        "priority": payload.priority.value,
                    },
                )
            ],
            created_at=now,
            updated_at=now,
        )

        queue_name = job.priority.value
        queue_item_id = self._queue.enqueue(
            payload={
                "job_id": str(job.id),
                "job_type": job.job_type,
                "priority": job.priority.value,
                "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
                "metadata": dict(job.metadata or {}),
            },
            queue_name=queue_name,
        )
        job.metadata.update(
            {
                "queue": {
                    "provider": "placeholder",
                    "queue_name": queue_name,
                    "item_id": queue_item_id,
                }
            }
        )

        self._items[job.id] = job
        return job

    def get_job(self, job_id: UUID) -> BackgroundJobResponse | None:
        return self._items.get(job_id)

    def list_jobs(self, filters: BackgroundJobFilter | None = None) -> BackgroundJobListResponse:
        query = filters or BackgroundJobFilter()
        records = list(self._items.values())
        records = [item for item in records if self._matches(item, query)]
        records.sort(key=lambda item: item.created_at, reverse=True)

        total = len(records)
        paged = records[query.offset : query.offset + query.limit]
        return BackgroundJobListResponse(items=paged, total=total)

    def update_job_status(
        self,
        job_id: UUID,
        status: BackgroundJobStatus,
        details: dict[str, object] | None = None,
    ) -> BackgroundJobResponse | None:
        job = self._items.get(job_id)
        if job is None:
            return None

        now = self._now_provider()
        previous = job.status
        job.status = status
        job.updated_at = now

        if status == BackgroundJobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.FAILED, BackgroundJobStatus.CANCELLED}:
            job.finished_at = now
        if status == BackgroundJobStatus.CANCELLED:
            job.cancelled_at = now

        job.execution_history.append(
            BackgroundJobExecutionEvent(
                event="status_changed",
                timestamp=now,
                details={
                    "from": previous.value,
                    "to": status.value,
                    **(details or {}),
                },
            )
        )
        return job

    def register_retry(
        self,
        job_id: UUID,
        next_retry_at: datetime | None = None,
        details: dict[str, object] | None = None,
    ) -> BackgroundJobResponse | None:
        job = self._items.get(job_id)
        if job is None:
            return None

        now = self._now_provider()
        job.retry.retry_count += 1
        job.retry.next_retry_at = next_retry_at
        job.status = BackgroundJobStatus.QUEUED if next_retry_at is None or next_retry_at <= now else BackgroundJobStatus.SCHEDULED
        job.updated_at = now

        job.execution_history.append(
            BackgroundJobExecutionEvent(
                event="retry_registered",
                timestamp=now,
                details={
                    "retry_count": job.retry.retry_count,
                    "max_retries": job.retry.max_retries,
                    "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
                    **(details or {}),
                },
            )
        )
        return job

    def cancel_job(self, job_id: UUID, reason: str | None = None) -> BackgroundJobResponse | None:
        job = self._items.get(job_id)
        if job is None:
            return None

        if job.status in {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.FAILED, BackgroundJobStatus.CANCELLED}:
            return job

        return self.update_job_status(
            job_id=job_id,
            status=BackgroundJobStatus.CANCELLED,
            details={"reason": reason} if reason else {},
        )

    def get_job_history(self, job_id: UUID) -> list[BackgroundJobExecutionEvent]:
        job = self._items.get(job_id)
        if job is None:
            return []
        return list(job.execution_history)

    def _matches(self, item: BackgroundJobResponse, filters: BackgroundJobFilter) -> bool:
        if filters.job_type is not None and item.job_type != filters.job_type:
            return False
        if filters.status is not None and item.status != filters.status:
            return False
        if filters.priority is not None and item.priority != filters.priority:
            return False
        if filters.scheduled_after is not None and (item.scheduled_at is None or item.scheduled_at < filters.scheduled_after):
            return False
        if filters.scheduled_before is not None and (item.scheduled_at is None or item.scheduled_at > filters.scheduled_before):
            return False
        if filters.created_after is not None and item.created_at < filters.created_after:
            return False
        if filters.created_before is not None and item.created_at > filters.created_before:
            return False
        return True
