"""Worker process for executing durable PostgreSQL-backed jobs."""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.runtime_validation import validate_worker_runtime
from app.db.database import SessionLocal
from app.repositories.durable_job import DurableJobRepository
from app.services.calendar_provider import FakeCalendarProvider
from app.services.durable_job_service import DurableJobService
from app.services.email_delivery import EmailDeliveryService
from app.services.job_handlers import register_default_job_handlers
from app.services.webhook_delivery import WebhookDeliveryService

logger = logging.getLogger("app.durable_job_worker")


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class DurableJobWorker:
    """Horizontally scalable worker — claims jobs via database locking."""

    def __init__(
        self,
        job_service: DurableJobService,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        validate_worker_runtime(settings)
        self.job_service = job_service
        self.worker_id = worker_id or default_worker_id()
        self.poll_interval_seconds = poll_interval_seconds or float(
            settings.DURABLE_JOB_WORKER_POLL_SECONDS
        )
        self._shutdown = threading.Event()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def process_one(self, job_types: list[str] | None = None) -> bool:
        db = self.job_service.repository.db
        try:
            job = self.job_service.claim_next(worker_id=self.worker_id, job_types=job_types)
            if job is None:
                return False
            self.job_service.execute_claimed(job)
            db.commit()
            return True
        except Exception:
            db.rollback()
            logger.exception(
                "durable_job_worker_process_error worker_id=%s",
                self.worker_id,
            )
            return False

    def process_batch(
        self,
        *,
        max_jobs: int | None = None,
        job_types: list[str] | None = None,
    ) -> int:
        settings = get_settings()
        limit = max_jobs or int(settings.DURABLE_JOB_WORKER_BATCH_SIZE)
        processed = 0
        for _ in range(limit):
            if self._shutdown.is_set():
                break
            if not self.process_one(job_types=job_types):
                break
            processed += 1
        return processed

    def run_forever(self, job_types: list[str] | None = None) -> None:
        logger.info("durable_job_worker_started worker_id=%s", self.worker_id)
        while not self._shutdown.is_set():
            processed = self.process_batch(job_types=job_types)
            if processed == 0 and not self._shutdown.is_set():
                self._shutdown.wait(timeout=self.poll_interval_seconds)
        logger.info("durable_job_worker_stopped worker_id=%s", self.worker_id)


def build_job_service(
    db: Session,
    *,
    email_delivery: EmailDeliveryService | None = None,
    webhook_delivery: WebhookDeliveryService | None = None,
    fake_calendar_provider: FakeCalendarProvider | None = None,
) -> DurableJobService:
    """Factory: repository + default handlers."""
    service = DurableJobService(DurableJobRepository(db))
    register_default_job_handlers(
        service,
        db,
        email_delivery=email_delivery,
        webhook_delivery=webhook_delivery,
        fake_calendar_provider=fake_calendar_provider,
    )
    return service


def _install_signal_handlers(worker: DurableJobWorker) -> None:
    def _handle_signal(signum: int, _frame) -> None:  # noqa: ANN001
        logger.info("durable_job_worker_shutdown_signal worker_id=%s signal=%s", worker.worker_id, signum)
        worker.request_shutdown()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def run_worker_process() -> None:
    """Entry point for standalone worker processes."""
    settings = get_settings()
    validate_worker_runtime(settings)
    worker_id = default_worker_id()
    db = SessionLocal()
    try:
        service = build_job_service(db)
        worker = DurableJobWorker(service, worker_id=worker_id)
        _install_signal_handlers(worker)
        worker.run_forever()
    finally:
        db.close()


if __name__ == "__main__":
    run_worker_process()
