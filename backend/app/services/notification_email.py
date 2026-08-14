"""Notification → email orchestration boundary.

Persisted in-app notifications remain the source of truth. Eligible events are
queued as durable jobs; workers perform SMTP delivery via EmailDeliveryService.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.durable_job import DurableJobType
from app.core.notification import (
    EMAIL_ELIGIBLE_EVENT_RECIPIENTS,
    NotificationEventType,
    NotificationRecipientType,
)
from app.schemas.durable_job import DurableJobSubmit
from app.schemas.email_delivery import (
    EmailAddress,
    EmailDeliveryResult,
    EmailDeliveryStatus,
    EmailMessage,
)
from app.schemas.notification import NotificationResponse
from app.services.durable_job_service import DurableJobService
from app.services.email_delivery import EmailDeliveryService

logger = logging.getLogger("app.notification_email")

_CANDIDATE_EMAIL_SAFE_KEYS = frozenset(
    {
        "event_type",
        "application_id",
        "job_id",
        "company_id",
        "status",
        "previous_status",
        "interview_id",
        "interview_type",
        "offer_id",
        "offer_status",
        "job_title",
    }
)


class NotificationEmailOrchestrator:
    """Maps eligible notification events to durable email jobs or worker delivery."""

    def __init__(
        self,
        email_delivery: EmailDeliveryService | None = None,
        job_service: DurableJobService | None = None,
        preference_service: Any | None = None,
    ) -> None:
        self.email_delivery = email_delivery or EmailDeliveryService()
        self.job_service = job_service
        self.preference_service = preference_service

    def is_email_eligible(
        self,
        *,
        event_type: str | NotificationEventType | None,
        recipient_type: NotificationRecipientType | str,
    ) -> bool:
        if event_type is None:
            return False
        try:
            event = (
                event_type
                if isinstance(event_type, NotificationEventType)
                else NotificationEventType(str(event_type))
            )
            recipient = (
                recipient_type
                if isinstance(recipient_type, NotificationRecipientType)
                else NotificationRecipientType(str(recipient_type))
            )
        except ValueError:
            return False
        return (event, recipient) in EMAIL_ELIGIBLE_EVENT_RECIPIENTS

    def enqueue_for_notification(
        self,
        *,
        notification: NotificationResponse,
        recipient_email: str | None = None,
        recipient_display_name: str | None = None,
    ) -> None:
        """Queue durable email delivery — HTTP/domain path does not wait on SMTP."""
        _ = recipient_email
        _ = recipient_display_name
        event_type = (notification.metadata or {}).get("event_type")
        if not self.is_email_eligible(
            event_type=event_type,
            recipient_type=notification.recipient_type,
        ):
            return

        if self.preference_service is not None:
            allowed = self.preference_service.is_email_allowed(
                recipient_type=notification.recipient_type,
                recipient_id=notification.recipient_id,
                company_id=notification.company_id,
                category=notification.category,
            )
            if not allowed:
                logger.info(
                    "email_enqueue_skipped_preference notification_id=%s event_type=%s category=%s",
                    notification.id,
                    event_type,
                    notification.category,
                )
                return

        if self.job_service is None:
            logger.warning(
                "email_enqueue_skipped_no_job_service notification_id=%s event_type=%s",
                notification.id,
                event_type,
            )
            return

        correlation_id = self._correlation_id(notification)
        self.job_service.submit(
            DurableJobSubmit(
                job_type=DurableJobType.EMAIL_DELIVERY,
                payload={"notification_id": str(notification.id)},
                idempotency_key=f"email:{correlation_id}",
                correlation_id=correlation_id,
                company_id=notification.company_id,
            )
        )

    def deliver_sync(
        self,
        *,
        notification: NotificationResponse,
        recipient_email: str | None,
        recipient_display_name: str | None = None,
    ) -> EmailDeliveryResult | None:
        """Synchronous delivery — workers only, not request handlers."""
        event_type = (notification.metadata or {}).get("event_type")
        if not self.is_email_eligible(
            event_type=event_type,
            recipient_type=notification.recipient_type,
        ):
            return None

        if not recipient_email or not str(recipient_email).strip():
            logger.warning(
                "email_skipped_missing_recipient event_type=%s notification_id=%s recipient_type=%s",
                event_type,
                notification.id,
                notification.recipient_type,
            )
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.SKIPPED,
                provider=self.email_delivery.provider.name,
                message="Trusted recipient email unavailable",
                correlation_id=self._correlation_id(notification),
                notification_id=notification.id,
            )

        try:
            to = EmailAddress(email=recipient_email, display_name=recipient_display_name)
        except Exception:
            logger.warning(
                "email_skipped_invalid_recipient event_type=%s notification_id=%s",
                event_type,
                notification.id,
            )
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=self.email_delivery.provider.name,
                message="Invalid trusted recipient email",
                correlation_id=self._correlation_id(notification),
                notification_id=notification.id,
            )

        subject, body = self._render(notification)
        safe_meta = self._outbound_metadata(notification)

        message = EmailMessage(
            to=to,
            subject=subject,
            body_text=body,
            correlation_id=self._correlation_id(notification),
            notification_id=notification.id,
            event_type=str(event_type) if event_type else None,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            company_id=notification.company_id,
            metadata=safe_meta,
        )
        return self.email_delivery.send(message)

    def dispatch_for_notification(
        self,
        *,
        notification: NotificationResponse,
        recipient_email: str | None,
        recipient_display_name: str | None = None,
    ) -> EmailDeliveryResult | None:
        """Backward-compatible alias for worker/tests."""
        return self.deliver_sync(
            notification=notification,
            recipient_email=recipient_email,
            recipient_display_name=recipient_display_name,
        )

    def _render(self, notification: NotificationResponse) -> tuple[str, str]:
        event_raw = (notification.metadata or {}).get("event_type")
        try:
            event = NotificationEventType(str(event_raw))
        except ValueError:
            event = None

        title = (notification.title or "Notification").strip()
        message = (notification.message or "").strip()
        meta = notification.metadata or {}

        if notification.recipient_type == NotificationRecipientType.CANDIDATE:
            meta = {k: v for k, v in meta.items() if k in _CANDIDATE_EMAIL_SAFE_KEYS}
            if event == NotificationEventType.INTERVIEW_SCHEDULED:
                job_title = meta.get("job_title")
                body = (
                    f"An interview has been scheduled for your {job_title} application."
                    if job_title
                    else "An interview has been scheduled for your application."
                )
                return "Interview scheduled", body
            if event == NotificationEventType.OFFER_APPROVED:
                job_title = meta.get("job_title")
                body = (
                    f"You have received an offer for {job_title}."
                    if job_title
                    else "You have received a job offer."
                )
                return "Offer available", body
            return title, message

        if event == NotificationEventType.OFFER_ACCEPTED:
            return "Offer accepted", message or "A candidate accepted an offer."
        if event == NotificationEventType.OFFER_DECLINED:
            return "Offer declined", message or "A candidate declined an offer."
        return title, message

    @staticmethod
    def _correlation_id(notification: NotificationResponse) -> str:
        event = (notification.metadata or {}).get("event_type") or "unknown"
        entity = notification.entity_id or notification.id
        return f"{event}:{entity}:{notification.recipient_type.value}:{notification.recipient_id}"

    @staticmethod
    def _outbound_metadata(notification: NotificationResponse) -> dict[str, Any]:
        meta = dict(notification.metadata or {})
        if notification.recipient_type == NotificationRecipientType.CANDIDATE:
            return {k: v for k, v in meta.items() if k in _CANDIDATE_EMAIL_SAFE_KEYS}
        blocked_substrings = ("password", "token", "secret", "jwt", "authorization", "api_key")
        return {
            k: v
            for k, v in meta.items()
            if not any(part in str(k).lower() for part in blocked_substrings)
        }
