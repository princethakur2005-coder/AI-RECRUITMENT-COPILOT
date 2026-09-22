"""Default durable job handler registrations."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.durable_job import DurableJobType
from app.services.calendar_provider import FakeCalendarProvider
from app.services.durable_job_service import DurableJobService
from app.services.email_delivery import EmailDeliveryService
from app.services.job_handlers.calendar_sync import CalendarSyncJobHandler
from app.services.job_handlers.email_delivery import EmailDeliveryJobHandler
from app.services.job_handlers.resume_intelligence import ResumeIntelligenceJobHandler
from app.services.job_handlers.webhook_delivery import WebhookDeliveryJobHandler
from app.services.webhook_delivery import WebhookDeliveryService


def register_default_job_handlers(
    service: DurableJobService,
    db: Session,
    *,
    email_delivery: EmailDeliveryService | None = None,
    webhook_delivery: WebhookDeliveryService | None = None,
    fake_calendar_provider: FakeCalendarProvider | None = None,
) -> None:
    email_handler = EmailDeliveryJobHandler(db, email_delivery=email_delivery)
    service.register_handler(DurableJobType.EMAIL_DELIVERY, email_handler.execute)

    webhook_handler = WebhookDeliveryJobHandler(db, delivery_service=webhook_delivery)
    service.register_handler(DurableJobType.WEBHOOK_DELIVERY, webhook_handler.execute)

    calendar_handler = CalendarSyncJobHandler(db, fake_provider=fake_calendar_provider)
    service.register_handler(DurableJobType.CALENDAR_SYNC, calendar_handler.execute)

    resume_handler = ResumeIntelligenceJobHandler(db)
    service.register_handler(DurableJobType.RESUME_INTELLIGENCE, resume_handler.execute)
    service.register_handler("process_resume_intelligence", resume_handler.execute)

