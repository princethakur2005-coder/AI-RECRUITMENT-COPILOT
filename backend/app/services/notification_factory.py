"""Factory helpers for notification + durable job + webhook + calendar wiring."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.durable_job import DurableJobRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.repositories.notification import NotificationRepository
from app.repositories.notification_preference import NotificationPreferenceRepository
from app.repositories.webhook import WebhookRepository
from app.services.calendar_provider import FakeCalendarProvider
from app.services.calendar_sync import CalendarSyncService
from app.services.durable_job_service import DurableJobService
from app.services.email_delivery import EmailDeliveryService
from app.services.job_handlers import register_default_job_handlers
from app.services.notification import NotificationService
from app.services.notification_email import NotificationEmailOrchestrator
from app.services.notification_events import NotificationEventProducer
from app.services.notification_preference import NotificationPreferenceService
from app.services.webhook_delivery import WebhookDeliveryService
from app.services.webhook_events import WebhookEventDispatcher


def build_preference_service(db: Session) -> NotificationPreferenceService:
    return NotificationPreferenceService(
        NotificationPreferenceRepository(db),
        CompanyMemberRepository(db),
    )


def build_notification_service(db: Session) -> NotificationService:
    member_repository = CompanyMemberRepository(db)
    return NotificationService(
        NotificationRepository(db),
        member_repository,
        preference_service=build_preference_service(db),
    )


def build_durable_job_service(
    db: Session,
    *,
    email_delivery: EmailDeliveryService | None = None,
    webhook_delivery: WebhookDeliveryService | None = None,
    fake_calendar_provider: FakeCalendarProvider | None = None,
) -> DurableJobService:
    service = DurableJobService(DurableJobRepository(db))
    register_default_job_handlers(
        service,
        db,
        email_delivery=email_delivery,
        webhook_delivery=webhook_delivery,
        fake_calendar_provider=fake_calendar_provider,
    )
    return service


def build_calendar_sync_service(
    db: Session,
    *,
    job_service: DurableJobService | None = None,
    email_delivery: EmailDeliveryService | None = None,
    webhook_delivery: WebhookDeliveryService | None = None,
    fake_calendar_provider: FakeCalendarProvider | None = None,
) -> CalendarSyncService:
    resolved_jobs = job_service or build_durable_job_service(
        db,
        email_delivery=email_delivery,
        webhook_delivery=webhook_delivery,
        fake_calendar_provider=fake_calendar_provider,
    )
    return CalendarSyncService(
        InterviewCalendarSyncRepository(db),
        CalendarIntegrationRepository(db),
        InterviewRepository(db),
        job_service=resolved_jobs,
    )


def build_notification_event_producer(
    db: Session,
    *,
    email_delivery: EmailDeliveryService | None = None,
    webhook_delivery: WebhookDeliveryService | None = None,
    fake_calendar_provider: FakeCalendarProvider | None = None,
) -> NotificationEventProducer:
    member_repository = CompanyMemberRepository(db)
    preference_service = build_preference_service(db)
    notification_service = NotificationService(
        NotificationRepository(db),
        member_repository,
        preference_service=preference_service,
    )
    job_service = build_durable_job_service(
        db,
        email_delivery=email_delivery,
        webhook_delivery=webhook_delivery,
        fake_calendar_provider=fake_calendar_provider,
    )
    email_orchestrator = NotificationEmailOrchestrator(
        email_delivery=email_delivery,
        job_service=job_service,
        preference_service=preference_service,
    )
    webhook_dispatcher = WebhookEventDispatcher(
        WebhookRepository(db),
        job_service=job_service,
    )
    return NotificationEventProducer(
        notification_service,
        member_repository,
        email_orchestrator=email_orchestrator,
        webhook_dispatcher=webhook_dispatcher,
    )
