"""Durable PostgreSQL-backed background job foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.durable_job import (
    DurableJobStatus,
    DurableJobType,
    JobExecutionError,
    validate_job_transition,
)
from app.db.base import Base
from app.models.durable_job import DurableJob
from app.repositories.durable_job import DurableJobRepository
from app.schemas.durable_job import DurableJobSubmit
from app.services.durable_job_service import DurableJobService
from app.services.durable_job_worker import DurableJobWorker

import app.models  # noqa: F401 — register metadata


@pytest.fixture
def job_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _service(db: Session) -> DurableJobService:
    return DurableJobService(DurableJobRepository(db))


def test_job_creation_persisted(job_db: Session) -> None:
    service = _service(job_db)
    created = service.submit(
        DurableJobSubmit(
            job_type=DurableJobType.EMAIL_DELIVERY,
            payload={"notification_id": str(uuid4())},
            idempotency_key="email:test:1",
            correlation_id="corr-1",
        )
    )
    assert created.status == DurableJobStatus.PENDING
    row = job_db.get(DurableJob, created.id)
    assert row is not None
    assert row.job_type == DurableJobType.EMAIL_DELIVERY.value


def test_valid_lifecycle_transitions() -> None:
    assert validate_job_transition(DurableJobStatus.PENDING, DurableJobStatus.RUNNING) == DurableJobStatus.RUNNING
    assert validate_job_transition(DurableJobStatus.RUNNING, DurableJobStatus.SUCCEEDED) == DurableJobStatus.SUCCEEDED


def test_invalid_lifecycle_transition_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid durable job transition"):
        validate_job_transition(DurableJobStatus.SUCCEEDED, DurableJobStatus.RUNNING)


def test_two_workers_cannot_claim_same_job(job_db: Session) -> None:
    service = _service(job_db)
    submitted = service.submit(
        DurableJobSubmit(
            job_type="test.noop",
            payload={},
            idempotency_key="job:unique:1",
        )
    )
    service.register_handler("test.noop", lambda _job: None)

    worker_a = DurableJobWorker(service, worker_id="worker-a")
    worker_b = DurableJobWorker(service, worker_id="worker-b")

    assert worker_a.process_one() is True
  # job now RUNNING
    assert worker_b.process_one() is False


def test_idempotent_duplicate_submission(job_db: Session) -> None:
    service = _service(job_db)
    first = service.submit(
        DurableJobSubmit(
            job_type=DurableJobType.EMAIL_DELIVERY,
            payload={"notification_id": str(uuid4())},
            idempotency_key="email:dup:1",
        )
    )
    second = service.submit(
        DurableJobSubmit(
            job_type=DurableJobType.EMAIL_DELIVERY,
            payload={"notification_id": str(uuid4())},
            idempotency_key="email:dup:1",
        )
    )
    assert first.id == second.id
    rows = list(job_db.scalars(select(DurableJob).where(DurableJob.idempotency_key == "email:dup:1")).all())
    assert len(rows) == 1


def test_retryable_failure_schedules_retry(job_db: Session) -> None:
    service = _service(job_db)

    def _fail(_job: DurableJob) -> None:
        raise JobExecutionError("smtp down", retryable=True, error_code="smtp")

    service.register_handler("test.retry", _fail)
    service.submit(
        DurableJobSubmit(job_type="test.retry", payload={}, idempotency_key="retry:1", max_attempts=3),
    )
    worker = DurableJobWorker(service, worker_id="w1")
    worker.process_one()

    row = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "retry:1"))
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_RETRYABLE.value
    assert row.attempt_count == 1
    assert row.next_run_at is not None


def test_permanent_failure_stops_retrying(job_db: Session) -> None:
    service = _service(job_db)

    def _boom(_job: DurableJob) -> None:
        raise JobExecutionError("bad payload", retryable=False, error_code="invalid")

    service.register_handler("test.permanent", _boom)
    service.submit(
        DurableJobSubmit(job_type="test.permanent", payload={}, idempotency_key="perm:1", max_attempts=5),
    )
    DurableJobWorker(service, worker_id="w1").process_one()

    row = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "perm:1"))
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_PERMANENT.value


def test_max_retry_attempts_respected(job_db: Session) -> None:
    service = _service(job_db)

    def _fail(_job: DurableJob) -> None:
        raise JobExecutionError("fail", retryable=True)

    service.register_handler("test.max", _fail)
    service.submit(
        DurableJobSubmit(job_type="test.max", payload={}, idempotency_key="max:1", max_attempts=2),
    )
    worker = DurableJobWorker(service, worker_id="w1")
    worker.process_one()
    row = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "max:1"))
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_RETRYABLE.value

    row.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    job_db.add(row)
    job_db.commit()

    worker.process_one()
    job_db.refresh(row)
    assert row.status == DurableJobStatus.FAILED_PERMANENT.value
    assert row.attempt_count >= 2


def test_stale_running_job_recovery(job_db: Session) -> None:
    service = _service(job_db)
    now = datetime.now(timezone.utc)
    stale = DurableJob(
        job_type="test.stale",
        status=DurableJobStatus.RUNNING.value,
        payload_json={},
        attempt_count=0,
        max_attempts=5,
        locked_at=now - timedelta(seconds=600),
        locked_by="dead-worker",
    )
    job_db.add(stale)
    job_db.commit()

    recovered = service.recover_stale_jobs(now=now)
    assert recovered == 1
    job_db.refresh(stale)
    assert stale.status == DurableJobStatus.FAILED_RETRYABLE.value


def test_successful_handler_marks_job_succeeded(job_db: Session) -> None:
    service = _service(job_db)
    service.register_handler("test.ok", lambda _job: None)
    service.submit(DurableJobSubmit(job_type="test.ok", payload={}, idempotency_key="ok:1"))
    DurableJobWorker(service, worker_id="w1").process_one()
    row = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "ok:1"))
    assert row is not None
    assert row.status == DurableJobStatus.SUCCEEDED.value


def test_running_job_is_not_claimed_by_another_worker(job_db: Session) -> None:
    service = _service(job_db)
    now = datetime.now(timezone.utc)
    running = DurableJob(
        job_type="test.running",
        status=DurableJobStatus.RUNNING.value,
        payload_json={},
        attempt_count=0,
        max_attempts=3,
        locked_at=now,
        locked_by="worker-a",
    )
    job_db.add(running)
    job_db.commit()

    claimed = service.claim_next(worker_id="worker-b")
    assert claimed is None


def test_execute_claimed_skips_terminal_jobs(job_db: Session) -> None:
    service = _service(job_db)
    calls = {"count": 0}

    def _handler(_job: DurableJob) -> None:
        calls["count"] += 1

    service.register_handler("test.terminal", _handler)
    completed = DurableJob(
        job_type="test.terminal",
        status=DurableJobStatus.SUCCEEDED.value,
        payload_json={},
        attempt_count=1,
        max_attempts=3,
        completed_at=datetime.now(timezone.utc),
    )
    job_db.add(completed)
    job_db.commit()

    response = service.execute_claimed(completed)
    assert response.status == DurableJobStatus.SUCCEEDED
    assert calls["count"] == 0


def test_stale_recovery_does_not_touch_recent_running_jobs(job_db: Session) -> None:
    service = _service(job_db)
    now = datetime.now(timezone.utc)
    running = DurableJob(
        job_type="test.active",
        status=DurableJobStatus.RUNNING.value,
        payload_json={},
        attempt_count=0,
        max_attempts=5,
        locked_at=now - timedelta(seconds=30),
        locked_by="active-worker",
    )
    job_db.add(running)
    job_db.commit()

    recovered = service.recover_stale_jobs(now=now)
    assert recovered == 0
    job_db.refresh(running)
    assert running.status == DurableJobStatus.RUNNING.value
    assert running.locked_by == "active-worker"


def test_sensitive_handler_errors_are_redacted(job_db: Session) -> None:
    service = _service(job_db)

    def _fail(_job: DurableJob) -> None:
        raise JobExecutionError("smtp_password=super-secret failed", retryable=True, error_code="smtp")

    service.register_handler("test.secret", _fail)
    service.submit(
        DurableJobSubmit(job_type="test.secret", payload={}, idempotency_key="secret:1", max_attempts=3),
    )
    DurableJobWorker(service, worker_id="w1").process_one()

    row = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "secret:1"))
    assert row is not None
    assert row.error_message == "Job execution failed"
    assert "super-secret" not in (row.error_message or "")


def test_payload_secrets_are_stripped_on_submission(job_db: Session) -> None:
    service = _service(job_db)
    created = service.submit(
        DurableJobSubmit(
            job_type=DurableJobType.EMAIL_DELIVERY,
            payload={"notification_id": str(uuid4()), "smtp_password": "secret"},
            idempotency_key="payload:1",
        )
    )
    row = job_db.get(DurableJob, created.id)
    assert row is not None
    assert "smtp_password" not in row.payload_json
    assert "secret" not in str(row.payload_json)


def test_worker_isolates_handler_failures_and_continues_batch(job_db: Session) -> None:
    service = _service(job_db)

    def _fail(_job: DurableJob) -> None:
        raise RuntimeError("handler exploded")

    service.register_handler("test.batch_fail", _fail)
    service.register_handler("test.batch_ok", lambda _job: None)
    service.submit(DurableJobSubmit(job_type="test.batch_fail", payload={}, idempotency_key="batch:fail"))
    service.submit(DurableJobSubmit(job_type="test.batch_ok", payload={}, idempotency_key="batch:ok"))

    processed = DurableJobWorker(service, worker_id="w1").process_batch(max_jobs=2)
    assert processed == 2

    failed = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "batch:fail"))
    ok = job_db.scalar(select(DurableJob).where(DurableJob.idempotency_key == "batch:ok"))
    assert failed is not None
    assert ok is not None
    assert failed.status == DurableJobStatus.FAILED_RETRYABLE.value
    assert ok.status == DurableJobStatus.SUCCEEDED.value


def test_worker_graceful_shutdown_stops_polling(job_db: Session) -> None:
    service = _service(job_db)
    worker = DurableJobWorker(service, worker_id="shutdown-worker", poll_interval_seconds=0.01)
    worker.request_shutdown()
    worker.run_forever()
    assert worker._shutdown.is_set()
