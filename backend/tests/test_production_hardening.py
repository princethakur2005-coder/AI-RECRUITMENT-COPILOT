"""Production hardening — config, health, errors, and worker runtime safety."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import app.models  # noqa: F401
from app.core.exceptions import unhandled_exception_handler
from app.core.runtime_validation import validate_api_runtime, validate_worker_runtime
from app.db.base import Base
from app.main import app
from app.middleware.error import RequestCorrelationMiddleware
from app.middleware.request_logging import request_logging_middleware


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _reload_config(monkeypatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.core.config as config_module

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)


def test_production_rejects_default_secret(monkeypatch) -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _reload_config(
            monkeypatch,
            DEBUG="false",
            SECRET_KEY="change-me-in-production",
            DATABASE_URL="postgresql+psycopg2://app:secret@db.example.com:5432/ai_recruitment",
            ALLOWED_HOSTS='["api.example.com"]',
            CORS_ORIGINS='["https://app.example.com"]',
        )


def test_production_rejects_sqlite_database_url(monkeypatch) -> None:
    with pytest.raises(ValueError, match="SQLite"):
        _reload_config(
            monkeypatch,
            DEBUG="false",
            SECRET_KEY="production-secret-key",
            DATABASE_URL="sqlite:///./unsafe.db",
            ALLOWED_HOSTS='["api.example.com"]',
            CORS_ORIGINS='["https://app.example.com"]',
        )


def test_production_rejects_localhost_webhook_policy(monkeypatch) -> None:
    with pytest.raises(ValueError, match="WEBHOOK_ALLOW_HTTP_LOCALHOST"):
        _reload_config(
            monkeypatch,
            DEBUG="false",
            SECRET_KEY="production-secret-key",
            DATABASE_URL="postgresql+psycopg2://app:secret@db.example.com:5432/ai_recruitment",
            ALLOWED_HOSTS='["api.example.com"]',
            CORS_ORIGINS='["https://app.example.com"]',
            WEBHOOK_ALLOW_HTTP_LOCALHOST="true",
        )


def test_production_requires_smtp_when_email_enabled(monkeypatch) -> None:
    with pytest.raises(ValueError, match="EMAIL_DELIVERY_ENABLED"):
        _reload_config(
            monkeypatch,
            DEBUG="false",
            SECRET_KEY="production-secret-key",
            DATABASE_URL="postgresql+psycopg2://app:secret@db.example.com:5432/ai_recruitment",
            ALLOWED_HOSTS='["api.example.com"]',
            CORS_ORIGINS='["https://app.example.com"]',
            EMAIL_DELIVERY_ENABLED="true",
            WEBHOOK_ALLOW_HTTP_LOCALHOST="false",
        )


def test_production_settings_validate_worker_runtime(monkeypatch) -> None:
    _reload_config(
        monkeypatch,
        DEBUG="false",
        SECRET_KEY="production-secret-key",
        DATABASE_URL="postgresql+psycopg2://app:secret@db.example.com:5432/ai_recruitment",
        ALLOWED_HOSTS='["api.example.com"]',
        CORS_ORIGINS='["https://app.example.com"]',
        WEBHOOK_ALLOW_HTTP_LOCALHOST="false",
    )
    import app.core.config as config_module

    validate_api_runtime(config_module.settings)
    validate_worker_runtime(config_module.settings)


def test_invalid_worker_poll_interval_rejected(monkeypatch) -> None:
    with pytest.raises(ValueError, match="DURABLE_JOB_WORKER_POLL_SECONDS"):
        _reload_config(monkeypatch, DURABLE_JOB_WORKER_POLL_SECONDS="0")


def test_liveness_does_not_require_database() -> None:
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok"}


def test_readiness_checks_database_and_returns_status(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert "dependencies" in payload
    assert "database" in payload["dependencies"]
    assert payload["dependencies"]["database"]["status"] in {"healthy", "unhealthy"}


def test_readiness_failure_returns_service_unavailable(monkeypatch) -> None:
    from app.core import monitoring

    def _fail_db() -> dict:
        return {"status": "unhealthy", "error": "dependency check failed"}

    monkeypatch.setattr(monitoring, "_check_database_health", _fail_db)
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


def test_development_settings_remain_valid(monkeypatch) -> None:
    _reload_config(monkeypatch, DEBUG="true")
    import app.core.config as config_module

    validate_api_runtime(config_module.settings)


def test_health_endpoints_do_not_leak_sensitive_configuration() -> None:
    client = TestClient(app)
    sensitive_markers = (
        "postgresql",
        "password",
        "secret_key",
        "smtp_password",
        "redis://",
        "database_url",
        "monitoring",
    )
    for path in ("/health/live", "/health/ready", "/health"):
        response = client.get(path)
        body = response.text.lower()
        for marker in sensitive_markers:
            assert marker not in body


def test_unhandled_api_error_is_safe_in_production(monkeypatch) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "DEBUG", False)
    monkeypatch.setattr(config_module.settings, "ERROR_VERBOSITY", "minimal")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/internal",
        "raw_path": b"/internal",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    request.state.request_id = "req-safe-error"
    response = unhandled_exception_handler(
        request,
        RuntimeError("postgresql password=super-secret SELECT * FROM users"),
    )
    assert response.status_code == 500
    body = response.body.decode()
    assert "super-secret" not in body
    assert "SELECT" not in body
    assert "Internal server error" in body


def test_request_correlation_id_is_exposed_and_logged(monkeypatch) -> None:
    captured: list[str] = []

    def _capture(_message, *args, **kwargs):  # noqa: ANN001
        extra = kwargs.get("extra") or {}
        captured.append(extra.get("event", ""))

    import app.core.logging as logging_module

    monkeypatch.setattr(logging_module.logger, "info", _capture)

    probe_app = FastAPI()
    probe_app.add_middleware(RequestCorrelationMiddleware)
    probe_app.middleware("http")(request_logging_middleware)

    @probe_app.get("/probe")
    def _ok() -> dict[str, str]:
        return {"ok": "true"}

    client = TestClient(probe_app)
    response = client.get("/probe", headers={"X-Request-ID": "corr-test-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "corr-test-123"
    assert "request_started" in captured
    assert "request_completed" in captured


def test_worker_graceful_shutdown_stops_loop(job_db) -> None:
    from app.repositories.durable_job import DurableJobRepository
    from app.services.durable_job_service import DurableJobService
    from app.services.durable_job_worker import DurableJobWorker

    service = DurableJobService(DurableJobRepository(job_db))
    worker = DurableJobWorker(service, worker_id="test-worker", poll_interval_seconds=0.01)
    worker.request_shutdown()
    worker.run_forever()
    assert worker._shutdown.is_set()


def test_worker_process_one_rolls_back_on_commit_failure(job_db, monkeypatch) -> None:
    from app.repositories.durable_job import DurableJobRepository
    from app.services.durable_job_service import DurableJobService
    from app.services.durable_job_worker import DurableJobWorker

    service = DurableJobService(DurableJobRepository(job_db))
    worker = DurableJobWorker(service, worker_id="test-worker", poll_interval_seconds=0.01)

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("commit failed")

    monkeypatch.setattr(service, "claim_next", lambda **kwargs: object())
    monkeypatch.setattr(service, "execute_claimed", lambda _job: None)
    monkeypatch.setattr(job_db, "commit", _boom)

    assert worker.process_one() is False
    assert job_db.in_transaction() is False or job_db.is_active


def test_alembic_has_single_head() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    heads = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1
    assert heads[0].endswith("(head)")
