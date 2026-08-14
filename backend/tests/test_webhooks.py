"""Enterprise webhook configuration, signing, and durable delivery tests."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.durable_job import DurableJobStatus, DurableJobType, JobExecutionError
from app.core.notification import NotificationEventType
from app.core.secret_box import seal_secret, unseal_secret
from app.core.webhook import (
    sign_webhook_payload,
    validate_webhook_endpoint_url,
    verify_webhook_signature,
)
from app.db.base import Base
from app.models.durable_job import DurableJob
from app.models.user import User
from app.models.webhook import Webhook
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.durable_job import DurableJobRepository
from app.repositories.webhook import WebhookRepository
from app.schemas.durable_job import DurableJobSubmit
from app.schemas.webhook import WebhookCreate, WebhookEventEnvelope, WebhookUpdate
from app.services.durable_job_service import DurableJobService
from app.services.durable_job_worker import DurableJobWorker
from app.services.job_handlers import register_default_job_handlers
from app.services.webhook_delivery import (
    WebhookDeliveryRequest,
    WebhookDeliveryService,
)
from app.services.webhook_events import WebhookEventDispatcher
from app.services.webhook_service import WebhookService
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


class RecordingTransport:
    def __init__(self, *, status_code: int = 200, raise_timeout: bool = False) -> None:
        self.calls: list[dict] = []
        self.status_code = status_code
        self.raise_timeout = raise_timeout

    def post(
        self,
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append(
            {
                "url": url,
                "content": content,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if self.raise_timeout:
            raise httpx.TimeoutException("timed out", request=None)
        return self.status_code, b"ok"


@pytest.fixture
def webhook_settings(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "WEBHOOK_SKIP_DNS_VALIDATION", True)
    monkeypatch.setattr(settings, "WEBHOOK_VALIDATE_DNS", False)
    monkeypatch.setattr(settings, "DEBUG", True)
    return settings


@pytest.fixture
def admin_user(world: OfferWorld) -> User:
    admin = User(
        full_name="Admin User",
        email=f"admin-{uuid4().hex[:8]}@acme.test",
        hashed_password="hashed",
        role="company_admin",
        company_id=world.company.id,
        is_active=True,
    )
    world.db.add(admin)
    world.db.flush()
    from app.models.company_member import CompanyMember

    world.db.add(
        CompanyMember(
            company_id=world.company.id,
            user_id=admin.id,
            role="company_admin",
            is_active=True,
        )
    )
    world.db.commit()
    return admin


def _webhook_service(world: OfferWorld) -> WebhookService:
    return WebhookService(
        WebhookRepository(world.db),
        CompanyRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _job_service(world: OfferWorld, transport: RecordingTransport) -> DurableJobService:
    service = DurableJobService(DurableJobRepository(world.db))
    register_default_job_handlers(
        service,
        world.db,
        webhook_delivery=WebhookDeliveryService(transport=transport),
    )
    return service


def test_tenant_scoped_webhook_creation(world: OfferWorld, admin_user: User, webhook_settings) -> None:
    service = _webhook_service(world)
    created = service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_ACCEPTED.value],
            description="Offer sink",
        ),
    )
    assert created.company_id == world.company.id
    assert created.signing_secret
    assert created.secret_hint == created.signing_secret[-4:]
    row = world.db.get(Webhook, created.id)
    assert row is not None
    assert row.signing_secret_sealed != created.signing_secret
    assert unseal_secret(row.signing_secret_sealed, webhook_settings.SECRET_KEY) == created.signing_secret


def test_cross_company_webhook_access_blocked(world: OfferWorld, admin_user: User, webhook_settings) -> None:
    service = _webhook_service(world)
    created = service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    # Foreign company path: do not leak existence (404 / LookupError).
    with pytest.raises(LookupError):
        service.get(world.other_recruiter, world.other_company.id, created.id)
    # Same webhook id under owning company, but foreign actor → 403.
    with pytest.raises(PermissionError):
        service.get(world.other_recruiter, world.company.id, created.id)
    with pytest.raises(LookupError):
        service.get(admin_user, world.company.id, uuid4())


def test_rbac_restrictions_enforced(world: OfferWorld, admin_user: User, webhook_settings) -> None:
    service = _webhook_service(world)
    with pytest.raises(PermissionError):
        service.create(
            world.recruiter,
            world.company.id,
            WebhookCreate(
                url="https://hooks.example.com/acme",
                event_types=[NotificationEventType.OFFER_CREATED.value],
            ),
        )
    created = service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    # Recruiters may list/get (company access) but not mutate.
    listed = service.list(world.recruiter, world.company.id)
    assert any(item.id == created.id for item in listed)
    with pytest.raises(PermissionError):
        service.set_active(world.recruiter, world.company.id, created.id, is_active=False)


def test_secrets_never_returned_by_normal_responses(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    service = _webhook_service(world)
    created = service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.INTERVIEW_SCHEDULED.value],
        ),
    )
    fetched = service.get(admin_user, world.company.id, created.id)
    dumped = fetched.model_dump()
    assert "signing_secret" not in dumped
    assert "signing_secret_sealed" not in dumped
    listed = service.list(admin_user, world.company.id)
    assert all("signing_secret" not in item.model_dump() for item in listed)


def test_event_subscription_validation(world: OfferWorld, admin_user: User, webhook_settings) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=["not.a.real.event"],
        )
    with pytest.raises(ValidationError):
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_APPROVED.value],
        )


def test_event_envelope_contract() -> None:
    company_id = uuid4()
    envelope = WebhookEventEnvelope(
        event_id="evt-1",
        event_type=NotificationEventType.APPLICATION_STATUS_CHANGED,
        occurred_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        company_id=company_id,
        data={
            "application_id": str(uuid4()),
            "status": "interview",
            "previous_status": "applied",
            "password": "secret",
            "ai_chain": "nope",
            "candidate_name": "should-strip",
        },
    )
    payload = envelope.to_delivery_dict()
    assert payload["api_version"] == "2026-08-13"
    assert payload["event_type"] == "application.status_changed"
    assert "password" not in payload["data"]
    assert "ai_chain" not in payload["data"]
    assert "candidate_name" not in payload["data"]
    assert payload["data"]["status"] == "interview"


def test_webhook_signature_deterministic_and_verifiable() -> None:
    secret = "whsec_test_secret"
    body = b'{"event_id":"1"}'
    timestamp = "1690000000"
    sig = sign_webhook_payload(secret=secret, timestamp=timestamp, body=body)
    assert sig.startswith("v1=")
    assert verify_webhook_signature(
        secret=secret,
        timestamp=timestamp,
        body=body,
        signature_header=sig,
    )
    assert sign_webhook_payload(secret=secret, timestamp=timestamp, body=body) == sig


def test_different_payload_or_event_ids_different_signatures() -> None:
    secret = "whsec_test_secret"
    ts = "1690000000"
    a = sign_webhook_payload(secret=secret, timestamp=ts, body=b'{"event_id":"a"}')
    b = sign_webhook_payload(secret=secret, timestamp=ts, body=b'{"event_id":"b"}')
    assert a != b


def test_webhook_delivery_uses_durable_jobs(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport()
    job_service = _job_service(world, transport)
    wh_service = _webhook_service(world)
    created = wh_service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_ACCEPTED.value],
        ),
    )
    dispatcher = WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service)
    count = dispatcher.dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_ACCEPTED,
        data={
            "offer_id": str(uuid4()),
            "application_id": str(world.application.id),
            "company_id": str(world.company.id),
            "status": "accepted",
            "offer_status": "accepted",
        },
        entity_key="offer:test:accepted",
        event_id="evt-offer-accepted-1",
    )
    assert count == 1
    jobs = list(
        world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.WEBHOOK_DELIVERY.value)
        ).all()
    )
    assert len(jobs) == 1
    assert jobs[0].idempotency_key == f"webhook:{created.id}:evt-offer-accepted-1"
    blob = json.dumps(jobs[0].payload_json)
    assert created.signing_secret not in blob
    assert "signing_secret" not in blob.lower()


def test_concurrent_workers_cannot_claim_same_webhook_job(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport()
    job_service = _job_service(world, transport)
    wh_service = _webhook_service(world)
    wh_service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_CREATED,
        data={"offer_id": str(uuid4()), "company_id": str(world.company.id), "offer_status": "draft"},
        event_id="evt-concurrent-1",
        entity_key="offer:concurrent",
    )
    worker_a = DurableJobWorker(job_service, worker_id="wa")
    worker_b = DurableJobWorker(job_service, worker_id="wb")
    assert worker_a.process_one() is True
    assert worker_b.process_one() is False


def test_successful_http_delivery_marks_job_succeeded(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport(status_code=200)
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_DECLINED.value],
        ),
    )
    WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_DECLINED,
        data={"offer_id": str(uuid4()), "company_id": str(world.company.id), "offer_status": "declined"},
        event_id="evt-success-1",
        entity_key="offer:success",
    )
    DurableJobWorker(job_service, worker_id="w1").process_one()
    row = world.db.scalar(
        select(DurableJob).where(DurableJob.idempotency_key == f"webhook:{created.id}:evt-success-1")
    )
    assert row is not None
    assert row.status == DurableJobStatus.SUCCEEDED.value
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert verify_webhook_signature(
        secret=created.signing_secret,
        timestamp=call["headers"]["X-Webhook-Timestamp"],
        body=call["content"],
        signature_header=call["headers"]["X-Webhook-Signature"],
    )


def test_retryable_http_failure_follows_policy(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport(status_code=503)
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.APPLICATION_STATUS_CHANGED.value],
        ),
    )
    WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.APPLICATION_STATUS_CHANGED,
        data={
            "application_id": str(world.application.id),
            "company_id": str(world.company.id),
            "status": "interview",
            "previous_status": "applied",
        },
        event_id="evt-retry-1",
        entity_key="app:retry",
    )
    DurableJobWorker(job_service, worker_id="w1").process_one()
    row = world.db.scalar(
        select(DurableJob).where(DurableJob.idempotency_key == f"webhook:{created.id}:evt-retry-1")
    )
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_RETRYABLE.value


def test_permanent_http_failure_stops_retrying(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport(status_code=400)
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.INTERVIEW_SCHEDULED.value],
        ),
    )
    WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.INTERVIEW_SCHEDULED,
        data={
            "interview_id": str(uuid4()),
            "application_id": str(world.application.id),
            "company_id": str(world.company.id),
            "interview_type": "phone",
            "status": "scheduled",
        },
        event_id="evt-perm-1",
        entity_key="interview:perm",
    )
    DurableJobWorker(job_service, worker_id="w1").process_one()
    row = world.db.scalar(
        select(DurableJob).where(DurableJob.idempotency_key == f"webhook:{created.id}:evt-perm-1")
    )
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_PERMANENT.value


def test_timeout_follows_retry_policy(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport(raise_timeout=True)
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_CREATED,
        data={"offer_id": str(uuid4()), "company_id": str(world.company.id), "offer_status": "draft"},
        event_id="evt-timeout-1",
        entity_key="offer:timeout",
    )
    DurableJobWorker(job_service, worker_id="w1").process_one()
    row = world.db.scalar(
        select(DurableJob).where(DurableJob.idempotency_key == f"webhook:{created.id}:evt-timeout-1")
    )
    assert row is not None
    assert row.status == DurableJobStatus.FAILED_RETRYABLE.value
    assert row.error_code == "timeout"


def test_duplicate_event_job_submission_idempotent(
    world: OfferWorld, admin_user: User, webhook_settings
) -> None:
    transport = RecordingTransport()
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_ACCEPTED.value],
        ),
    )
    dispatcher = WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service)
    payload = {
        "offer_id": str(uuid4()),
        "company_id": str(world.company.id),
        "offer_status": "accepted",
        "status": "accepted",
    }
    dispatcher.dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_ACCEPTED,
        data=payload,
        event_id="evt-dup-1",
        entity_key="offer:dup",
    )
    dispatcher.dispatch(
        company_id=world.company.id,
        event_type=NotificationEventType.OFFER_ACCEPTED,
        data=payload,
        event_id="evt-dup-1",
        entity_key="offer:dup",
    )
    jobs = list(
        world.db.scalars(
            select(DurableJob).where(
                DurableJob.idempotency_key == f"webhook:{created.id}:evt-dup-1"
            )
        ).all()
    )
    assert len(jobs) == 1


def test_secrets_not_written_to_logs(
    world: OfferWorld, admin_user: User, webhook_settings, caplog: pytest.LogCaptureFixture
) -> None:
    transport = RecordingTransport()
    job_service = _job_service(world, transport)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    with caplog.at_level(logging.DEBUG):
        WebhookEventDispatcher(WebhookRepository(world.db), job_service=job_service).dispatch(
            company_id=world.company.id,
            event_type=NotificationEventType.OFFER_CREATED,
            data={"offer_id": str(uuid4()), "company_id": str(world.company.id), "offer_status": "draft"},
            event_id="evt-log-1",
            entity_key="offer:log",
        )
        DurableJobWorker(job_service, worker_id="w1").process_one()
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert created.signing_secret not in combined


def test_ssrf_private_url_rejected(webhook_settings) -> None:
    with pytest.raises(ValueError):
        validate_webhook_endpoint_url(
            "https://127.0.0.1/hook",
            allow_http_localhost=False,
            resolve_dns=False,
        )
    with pytest.raises(ValueError):
        validate_webhook_endpoint_url(
            "http://example.com/hook",
            allow_http_localhost=False,
            resolve_dns=False,
        )


def test_enable_disable_update_delete(world: OfferWorld, admin_user: User, webhook_settings) -> None:
    service = _webhook_service(world)
    created = service.create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/acme",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    disabled = service.set_active(admin_user, world.company.id, created.id, is_active=False)
    assert disabled.is_active is False
    enabled = service.set_active(admin_user, world.company.id, created.id, is_active=True)
    assert enabled.is_active is True
    updated = service.update(
        admin_user,
        world.company.id,
        created.id,
        WebhookUpdate(description="Updated sink"),
    )
    assert updated.description == "Updated sink"
    service.delete(admin_user, world.company.id, created.id)
    assert world.db.get(Webhook, created.id) is None


def test_secret_box_roundtrip(webhook_settings) -> None:
    sealed = seal_secret("plain-secret-value", webhook_settings.SECRET_KEY)
    assert unseal_secret(sealed, webhook_settings.SECRET_KEY) == "plain-secret-value"
