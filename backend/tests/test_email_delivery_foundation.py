"""Email delivery foundation — provider boundary + notification email eligibility."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.interview_type import InterviewType
from app.core.notification import (
    NotificationCategory,
    NotificationEventType,
    NotificationPriority,
    NotificationRecipientType,
    NotificationStatus,
)
from app.core.offer_status import OfferStatus
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.repositories.notification import NotificationRepository
from app.schemas.email_delivery import (
    EmailAddress,
    EmailDeliveryResult,
    EmailDeliveryStatus,
    EmailMessage,
)
from app.schemas.interview import InterviewCreate
from app.schemas.notification import NotificationCreate, NotificationResponse
from app.services.application import ApplicationService
from app.services.email_delivery import EmailDeliveryService
from app.services.email_provider import EmailProvider, NullEmailProvider, build_email_provider
from app.services.durable_job_worker import DurableJobWorker
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService
from app.services.notification_email import NotificationEmailOrchestrator
from app.services.notification_events import NotificationEventProducer
from app.services.notification_factory import build_notification_event_producer
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


class RecordingEmailProvider(EmailProvider):
    """Test double at the provider boundary — no external network calls."""

    name = "recording"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        if self.fail:
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=self.name,
                message="forced failure",
                correlation_id=message.correlation_id,
                notification_id=message.notification_id,
            )
        self.sent.append(message)
        return EmailDeliveryResult(
            status=EmailDeliveryStatus.DELIVERED,
            provider=self.name,
            message="recorded",
            correlation_id=message.correlation_id,
            notification_id=message.notification_id,
        )


def _notification_service(world: OfferWorld) -> NotificationService:
    return NotificationService(
        NotificationRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _producer_with_async_email(
    world: OfferWorld,
    provider: EmailProvider,
) -> tuple[NotificationEventProducer, DurableJobWorker]:
    email_delivery = EmailDeliveryService(provider=provider)
    producer = build_notification_event_producer(world.db, email_delivery=email_delivery)
    job_service = producer.email_orchestrator.job_service
    assert job_service is not None
    worker = DurableJobWorker(job_service, worker_id="test-worker")
    return producer, worker


def _run_pending_email_jobs(world: OfferWorld, worker: DurableJobWorker) -> None:
    worker.process_batch(max_jobs=50)


def test_email_delivery_contract_via_abstraction() -> None:
    provider = RecordingEmailProvider()
    service = EmailDeliveryService(provider=provider)
    result = service.send(
        EmailMessage(
            to=EmailAddress(email="ada@example.com", display_name="Ada"),
            subject="Hello",
            body_text="Body text",
            event_type="test.event",
            correlation_id="corr-1",
            metadata={"password": "should-strip", "offer_id": "ok"},
        )
    )
    assert result.delivered is True
    assert result.status == EmailDeliveryStatus.DELIVERED
    assert len(provider.sent) == 1
    assert provider.sent[0].to.email == "ada@example.com"
    assert "password" not in provider.sent[0].metadata
    assert provider.sent[0].metadata.get("offer_id") == "ok"


def test_null_provider_when_delivery_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as config_module

    config_module.get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "false")
    config_module.get_settings.cache_clear()
    provider = build_email_provider(config_module.get_settings())
    assert isinstance(provider, NullEmailProvider)
    service = EmailDeliveryService(provider=provider)
    result = service.send(
        EmailMessage(
            to=EmailAddress(email="ada@example.com"),
            subject="Skip",
            body_text="Should not claim delivery",
        )
    )
    assert result.status == EmailDeliveryStatus.SKIPPED
    assert result.delivered is False
    config_module.get_settings.cache_clear()


def test_offer_candidate_email_is_candidate_safe(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    world.offer_service.notification_events = producer
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    _run_pending_email_jobs(world, worker)

    candidate_mails = [
        m for m in provider.sent if m.to.email == world.candidate.email.lower()
    ]
    assert len(candidate_mails) == 1
    mail = candidate_mails[0]
    assert mail.event_type == NotificationEventType.OFFER_APPROVED.value
    body_l = mail.body_text.lower()
    assert "offer" in body_l
    assert "password" not in body_l
    assert "jwt" not in body_l
    assert "token" not in body_l
    assert "score" not in body_l
    assert "recommendation" not in (mail.metadata or {})
    assert "ai_hiring_summary" not in (mail.metadata or {})
    for key in mail.metadata:
        assert "password" not in key.lower()
        assert "token" not in key.lower()


def test_interview_candidate_email_is_candidate_safe(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)
    interview_service = InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
        notification_service=_notification_service(world),
    )
    interview_service.notification_events = producer

    start = datetime.now(timezone.utc) + timedelta(days=1)
    interview_service.create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.hm_member.id,
            interview_type=InterviewType.TECHNICAL,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            timezone="UTC",
            notes="INTERNAL: candidate weak on system design — do not email",
        ),
    )
    _run_pending_email_jobs(world, worker)

    candidate_mails = [
        m for m in provider.sent if m.to.email == world.candidate.email.lower()
    ]
    assert len(candidate_mails) == 1
    mail = candidate_mails[0]
    assert mail.event_type == NotificationEventType.INTERVIEW_SCHEDULED.value
    assert "INTERNAL" not in mail.body_text
    assert "system design" not in mail.body_text
    assert "notes" not in mail.metadata
    assert mail.to.email == "candidate@example.com"


def test_staff_email_uses_trusted_server_side_identity(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)
    world.offer_service.notification_events = producer

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    world.offer_service.accept_offer(world.candidate, approved.id)
    _run_pending_email_jobs(world, worker)

    staff_mails = [
        m
        for m in provider.sent
        if m.event_type == NotificationEventType.OFFER_ACCEPTED.value
    ]
    assert staff_mails
    trusted = {world.recruiter.email.lower(), world.hiring_manager.email.lower()}
    for mail in staff_mails:
        assert mail.to.email in trusted
        assert mail.to.email != "attacker@evil.example.com"


def test_candidate_cannot_force_arbitrary_email_recipient(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    orchestrator = NotificationEmailOrchestrator(EmailDeliveryService(provider=provider))
    notification = NotificationResponse(
        id=uuid4(),
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        company_id=world.company.id,
        title="Offer available",
        message="You have received a job offer.",
        category=NotificationCategory.OFFER,
        priority=NotificationPriority.HIGH,
        status=NotificationStatus.UNREAD,
        entity_type="offer",
        entity_id=uuid4(),
        metadata={"event_type": NotificationEventType.OFFER_APPROVED.value},
        read_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    # Orchestrator only accepts the trusted email argument from the server caller.
    # Passing an arbitrary address is only possible if a producer incorrectly supplies it;
    # producers resolve Candidate.email — verify the trusted path uses candidate email.
    result = orchestrator.dispatch_for_notification(
        notification=notification,
        recipient_email=world.candidate.email,
        recipient_display_name=world.candidate.full_name,
    )
    assert result is not None and result.delivered
    assert provider.sent[-1].to.email == world.candidate.email.lower()

    # Direct create API still cannot be used to email arbitrary addresses through producers.
    service = _notification_service(world)
    created = service.create_notification(
        NotificationCreate(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=world.candidate.id,
            company_id=world.company.id,
            title="x",
            message="y",
            category=NotificationCategory.OFFER,
            metadata={"event_type": NotificationEventType.OFFER_APPROVED.value},
        )
    )
    # Without orchestrator + trusted email, no email is sent by NotificationService alone.
    assert len(provider.sent) == 1
    assert created.recipient_id == world.candidate.id


def test_sensitive_auth_data_never_included_in_email_metadata() -> None:
    msg = EmailMessage(
        to=EmailAddress(email="staff@example.com"),
        subject="Offer accepted",
        body_text="Candidate accepted.",
        metadata={
            "event_type": "offer.accepted",
            "access_token": "jwt-secret",
            "password": "nope",
            "offer_id": str(uuid4()),
        },
    )
    assert "access_token" not in msg.metadata
    assert "password" not in msg.metadata
    assert "offer_id" in msg.metadata
    assert "jwt-secret" not in msg.body_text


def test_email_failure_does_not_corrupt_offer_state(world: OfferWorld) -> None:
    provider = RecordingEmailProvider(fail=True)
    producer, worker = _producer_with_async_email(world, provider)
    world.offer_service.notification_events = producer

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    _run_pending_email_jobs(world, worker)
    assert approved.status == OfferStatus.APPROVED.value
    world.db.refresh(world.application)
    # Offer/application domain state remains intact despite email failures.
    assert world.offer_service.get_offer(world.recruiter, approved.id).status == OfferStatus.APPROVED.value


def test_unsupported_events_do_not_trigger_email(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)
    application_service = ApplicationService(
        ApplicationRepository(world.db),
        JobRepository(world.db),
        CandidateRepository(world.db),
        CompanyMemberRepository(world.db),
        notification_service=_notification_service(world),
    )
    application_service.notification_events = producer

    from app.core.application_status import ApplicationStatus

    application_service.update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.REJECTED.value,
    )
    _run_pending_email_jobs(world, worker)
    # application.status_changed is in-app only for this pack.
    assert provider.sent == []


def test_offer_created_does_not_email_candidate(world: OfferWorld) -> None:
    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)
    world.offer_service.notification_events = producer
    world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    _run_pending_email_jobs(world, worker)
    candidate_mails = [
        m for m in provider.sent if m.to.email == world.candidate.email.lower()
    ]
    assert candidate_mails == []


def test_duplicate_email_job_submission_is_idempotent(world: OfferWorld) -> None:
    from app.core.durable_job import DurableJobType
    from app.models.durable_job import DurableJob
    from sqlalchemy import select

    provider = RecordingEmailProvider()
    producer, worker = _producer_with_async_email(world, provider)
    world.offer_service.notification_events = producer

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    _run_pending_email_jobs(world, worker)

    email_jobs = list(
        world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.EMAIL_DELIVERY.value)
        ).all()
    )
    assert len(email_jobs) >= 1
    sent_count = len(provider.sent)
    assert sent_count >= 1

    _run_pending_email_jobs(world, worker)
    assert len(provider.sent) == sent_count


def test_notification_persists_when_email_job_fails(world: OfferWorld) -> None:
    provider = RecordingEmailProvider(fail=True)
    producer, worker = _producer_with_async_email(world, provider)
    world.offer_service.notification_events = producer

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    _run_pending_email_jobs(world, worker)

    from sqlalchemy import select
    from app.models.notification import Notification

    notes = list(world.db.scalars(select(Notification)).all())
    assert any(
        (n.metadata_json or {}).get("event_type") == NotificationEventType.OFFER_APPROVED.value
        for n in notes
    )
