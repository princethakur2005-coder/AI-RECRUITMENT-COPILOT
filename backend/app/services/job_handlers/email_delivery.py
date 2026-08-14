"""Execute notification email delivery jobs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.durable_job import JobExecutionError
from app.core.notification import NotificationRecipientType
from app.models.durable_job import DurableJob
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.schemas.email_delivery import EmailDeliveryStatus
from app.services.email_delivery import EmailDeliveryService
from app.services.notification_email import NotificationEmailOrchestrator


class EmailDeliveryJobHandler:
    """Loads notification + trusted recipient identity server-side; never trusts payload email."""

    def __init__(
        self,
        db: Session,
        *,
        email_delivery: EmailDeliveryService | None = None,
    ) -> None:
        self.db = db
        self.notification_repository = NotificationRepository(db)
        self.email_delivery = email_delivery or EmailDeliveryService()
        self.orchestrator = NotificationEmailOrchestrator(email_delivery=self.email_delivery)

    def execute(self, job: DurableJob) -> None:
        notification_id = job.payload.get("notification_id")
        if not notification_id:
            raise JobExecutionError(
                "Email delivery job missing notification_id",
                retryable=False,
                error_code="invalid_payload",
            )

        try:
            nid = UUID(str(notification_id))
        except ValueError:
            raise JobExecutionError(
                "Invalid notification_id in job payload",
                retryable=False,
                error_code="invalid_payload",
            )

        row = self.notification_repository.get_by_id(nid)
        if row is None:
            raise JobExecutionError(
                "Notification not found for email delivery",
                retryable=False,
                error_code="notification_not_found",
            )

        from app.schemas.notification import NotificationResponse

        notification = NotificationResponse.from_orm_notification(row)

        recipient_email, recipient_name = self._resolve_trusted_recipient(row)
        if not recipient_email:
            raise JobExecutionError(
                "Trusted recipient email unavailable",
                retryable=False,
                error_code="recipient_not_found",
            )

        if not self.orchestrator.is_email_eligible(
            event_type=(notification.metadata or {}).get("event_type"),
            recipient_type=notification.recipient_type,
        ):
            # Job should not have been queued — treat as permanent skip/success.
            return

        result = self.orchestrator.deliver_sync(
            notification=notification,
            recipient_email=recipient_email,
            recipient_display_name=recipient_name,
        )
        if result is None:
            return
        if result.status == EmailDeliveryStatus.DELIVERED:
            return
        if result.status == EmailDeliveryStatus.SKIPPED:
            return
        raise JobExecutionError(
            result.message or "Email delivery failed",
            retryable=True,
            error_code="email_delivery_failed",
        )

    def _resolve_trusted_recipient(self, notification_row) -> tuple[str | None, str | None]:
        recipient_type = notification_row.recipient_type
        recipient_id = notification_row.recipient_id

        if recipient_type == NotificationRecipientType.CANDIDATE.value:
            candidate = self.db.get(Candidate, recipient_id)
            if candidate is None or not candidate.email:
                return None, None
            return str(candidate.email).strip(), getattr(candidate, "full_name", None)

        if recipient_type == NotificationRecipientType.USER.value:
            user = self.db.get(User, recipient_id)
            if user is None or not user.email:
                return None, None
            return str(user.email).strip(), getattr(user, "full_name", None)

        return None, None
