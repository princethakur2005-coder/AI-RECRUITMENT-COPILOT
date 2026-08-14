"""Domain notification event producers.

Domain services call this layer after successful lifecycle mutations.
Recipient identity is derived from Application / Interview / Offer relationships —
never from client-supplied recipient IDs.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.notification import (
    INTERVIEW_STATUS_EVENT_MAP,
    NOTIFICATION_STAFF_ROLES,
    NotificationCategory,
    NotificationEventType,
    NotificationPriority,
    NotificationRecipientType,
)
from app.models.application import Application
from app.models.interview import Interview
from app.models.offer import Offer
from app.repositories.company_member import CompanyMemberRepository
from app.schemas.notification import NotificationCreate
from app.services.email_delivery import EmailDeliveryService
from app.services.notification import NotificationService
from app.services.notification_email import NotificationEmailOrchestrator

logger = logging.getLogger("app.notification_events")

# Candidate-facing payloads must stay privacy-safe (no AI scores, notes, or internal reasons).
_CANDIDATE_SAFE_METADATA_KEYS = frozenset(
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


class NotificationEventProducer:
    """Creates in-app notifications for supported domain lifecycle events.

    After a notification is persisted, eligible events may also be emailed through
    ``NotificationEmailOrchestrator`` and/or enqueued as durable webhook deliveries
    (transport is best-effort and never rolls back domain state).
    """

    def __init__(
        self,
        notification_service: NotificationService,
        member_repository: CompanyMemberRepository,
        email_delivery: EmailDeliveryService | None = None,
        email_orchestrator: NotificationEmailOrchestrator | None = None,
        webhook_dispatcher: Any | None = None,
    ) -> None:
        self.notification_service = notification_service
        self.member_repository = member_repository
        self.webhook_dispatcher = webhook_dispatcher
        if email_orchestrator is not None:
            self.email_orchestrator = email_orchestrator
        elif email_delivery is not None:
            self.email_orchestrator = NotificationEmailOrchestrator(email_delivery)
        else:
            # Default: settings-driven provider (often null/disabled in local/test).
            self.email_orchestrator = NotificationEmailOrchestrator()

    def application_status_changed(
        self,
        *,
        application: Application,
        previous_status: str,
        new_status: str,
    ) -> None:
        if previous_status == new_status:
            return

        job_title = self._job_title(application)
        candidate_name = self._candidate_name(application)
        base_meta = {
            "event_type": NotificationEventType.APPLICATION_STATUS_CHANGED.value,
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "company_id": str(application.company_id),
            "status": new_status,
            "previous_status": previous_status,
            "job_title": job_title,
        }

        self._safe_create(
            NotificationCreate(
                recipient_type=NotificationRecipientType.CANDIDATE,
                recipient_id=application.candidate_id,
                company_id=application.company_id,
                category=NotificationCategory.APPLICATION,
                priority=NotificationPriority.NORMAL,
                title="Application status updated",
                message=self._candidate_application_message(new_status, job_title),
                entity_type="application",
                entity_id=application.id,
                metadata=self._candidate_safe_metadata(base_meta),
            ),
            recipient_email=self._candidate_email(application),
            recipient_display_name=candidate_name,
        )

        staff_message = (
            f"{candidate_name}'s application"
            + (f" for {job_title}" if job_title else "")
            + f" moved from {previous_status} to {new_status}."
        )
        self._notify_staff(
            company_id=application.company_id,
            category=NotificationCategory.APPLICATION,
            title="Application status changed",
            message=staff_message,
            entity_type="application",
            entity_id=application.id,
            metadata={
                **base_meta,
                "candidate_id": str(application.candidate_id),
                "candidate_name": candidate_name,
            },
            priority=NotificationPriority.NORMAL,
        )
        self._dispatch_webhook(
            company_id=application.company_id,
            event_type=NotificationEventType.APPLICATION_STATUS_CHANGED,
            data={
                "application_id": str(application.id),
                "job_id": str(application.job_id),
                "company_id": str(application.company_id),
                "candidate_id": str(application.candidate_id),
                "status": new_status,
                "previous_status": previous_status,
                "job_title": job_title,
            },
            entity_key=f"application:{application.id}",
        )

    def interview_scheduled(self, *, interview: Interview, application: Application) -> None:
        job_title = self._job_title(application)
        candidate_name = self._candidate_name(application)
        base_meta = {
            "event_type": NotificationEventType.INTERVIEW_SCHEDULED.value,
            "interview_id": str(interview.id),
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "company_id": str(interview.company_id),
            "interview_type": interview.interview_type,
            "status": interview.status,
            "job_title": job_title,
        }

        self._safe_create(
            NotificationCreate(
                recipient_type=NotificationRecipientType.CANDIDATE,
                recipient_id=application.candidate_id,
                company_id=interview.company_id,
                category=NotificationCategory.INTERVIEW,
                priority=NotificationPriority.HIGH,
                title="Interview scheduled",
                message=self._candidate_interview_scheduled_message(job_title),
                entity_type="interview",
                entity_id=interview.id,
                metadata=self._candidate_safe_metadata(base_meta),
            ),
            recipient_email=self._candidate_email(application),
            recipient_display_name=candidate_name,
        )

        interviewer = self.member_repository.get_by_id_for_company(
            interview.interviewer_member_id,
            interview.company_id,
        )
        if interviewer is not None and interviewer.is_active:
            self._safe_create(
                NotificationCreate(
                    recipient_type=NotificationRecipientType.USER,
                    recipient_id=interviewer.user_id,
                    company_id=interview.company_id,
                    category=NotificationCategory.INTERVIEW,
                    priority=NotificationPriority.HIGH,
                    title="Interview assigned",
                    message=(
                        f"You are scheduled to interview {candidate_name}"
                        + (f" for {job_title}" if job_title else "")
                        + "."
                    ),
                    entity_type="interview",
                    entity_id=interview.id,
                    metadata={
                        **base_meta,
                        "candidate_id": str(application.candidate_id),
                        "candidate_name": candidate_name,
                        "interviewer_member_id": str(interview.interviewer_member_id),
                    },
                ),
                recipient_email=self._member_email(interviewer),
                recipient_display_name=self._member_display_name(interviewer),
            )

        self._dispatch_webhook(
            company_id=interview.company_id,
            event_type=NotificationEventType.INTERVIEW_SCHEDULED,
            data={
                "interview_id": str(interview.id),
                "application_id": str(application.id),
                "job_id": str(application.job_id),
                "company_id": str(interview.company_id),
                "candidate_id": str(application.candidate_id),
                "interview_type": interview.interview_type,
                "status": interview.status,
                "job_title": job_title,
            },
            entity_key=f"interview:{interview.id}",
        )

    def interview_status_changed(
        self,
        *,
        interview: Interview,
        application: Application,
        previous_status: str,
        new_status: str,
    ) -> None:
        if previous_status == new_status:
            return
        event_type = INTERVIEW_STATUS_EVENT_MAP.get(str(new_status))
        if event_type is None:
            return

        job_title = self._job_title(application)
        candidate_name = self._candidate_name(application)
        status_label = str(new_status).replace("_", " ")
        base_meta = {
            "event_type": event_type.value,
            "interview_id": str(interview.id),
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "company_id": str(interview.company_id),
            "interview_type": interview.interview_type,
            "status": str(new_status),
            "previous_status": previous_status,
            "job_title": job_title,
        }

        self._safe_create(
            NotificationCreate(
                recipient_type=NotificationRecipientType.CANDIDATE,
                recipient_id=application.candidate_id,
                company_id=interview.company_id,
                category=NotificationCategory.INTERVIEW,
                priority=NotificationPriority.NORMAL,
                title="Interview update",
                message=self._candidate_interview_status_message(status_label, job_title),
                entity_type="interview",
                entity_id=interview.id,
                metadata=self._candidate_safe_metadata(base_meta),
            ),
            recipient_email=self._candidate_email(application),
            recipient_display_name=candidate_name,
        )

        interviewer = self.member_repository.get_by_id_for_company(
            interview.interviewer_member_id,
            interview.company_id,
        )
        if interviewer is not None and interviewer.is_active:
            self._safe_create(
                NotificationCreate(
                    recipient_type=NotificationRecipientType.USER,
                    recipient_id=interviewer.user_id,
                    company_id=interview.company_id,
                    category=NotificationCategory.INTERVIEW,
                    priority=NotificationPriority.NORMAL,
                    title="Interview status updated",
                    message=(
                        f"Interview with {candidate_name}"
                        + (f" for {job_title}" if job_title else "")
                        + f" is now {status_label}."
                    ),
                    entity_type="interview",
                    entity_id=interview.id,
                    metadata={
                        **base_meta,
                        "candidate_id": str(application.candidate_id),
                        "candidate_name": candidate_name,
                        "interviewer_member_id": str(interview.interviewer_member_id),
                    },
                ),
                recipient_email=self._member_email(interviewer),
                recipient_display_name=self._member_display_name(interviewer),
            )

    def offer_created(self, *, offer: Offer, application: Application) -> None:
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_CREATED,
            offer=offer,
            application=application,
            staff_title="Offer created",
            staff_message_template="{candidate} offer draft created{job_clause}.",
            notify_candidate=False,
            candidate_title=None,
            candidate_message=None,
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.NORMAL,
        )

    def offer_submitted(self, *, offer: Offer, application: Application) -> None:
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_SUBMITTED,
            offer=offer,
            application=application,
            staff_title="Offer pending approval",
            staff_message_template="{candidate} offer submitted for approval{job_clause}.",
            notify_candidate=False,
            candidate_title=None,
            candidate_message=None,
            staff_roles=frozenset({"company_admin", "hiring_manager"}),
            priority=NotificationPriority.HIGH,
        )

    def offer_approved(self, *, offer: Offer, application: Application) -> None:
        job_title = self._job_title(application)
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_APPROVED,
            offer=offer,
            application=application,
            staff_title="Offer approved",
            staff_message_template="{candidate} offer approved{job_clause}.",
            notify_candidate=True,
            candidate_title="Offer available",
            candidate_message=self._candidate_offer_approved_message(job_title),
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.HIGH,
        )

    def offer_rejected(self, *, offer: Offer, application: Application) -> None:
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_REJECTED,
            offer=offer,
            application=application,
            staff_title="Offer rejected",
            staff_message_template="{candidate} offer was rejected during approval{job_clause}.",
            notify_candidate=False,
            candidate_title=None,
            candidate_message=None,
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.NORMAL,
        )

    def offer_accepted(self, *, offer: Offer, application: Application) -> None:
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_ACCEPTED,
            offer=offer,
            application=application,
            staff_title="Offer accepted",
            staff_message_template="{candidate} accepted the offer{job_clause}.",
            notify_candidate=False,
            candidate_title=None,
            candidate_message=None,
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.HIGH,
        )

    def offer_declined(self, *, offer: Offer, application: Application) -> None:
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_DECLINED,
            offer=offer,
            application=application,
            staff_title="Offer declined",
            staff_message_template="{candidate} declined the offer{job_clause}.",
            notify_candidate=False,
            candidate_title=None,
            candidate_message=None,
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.HIGH,
        )

    def offer_withdrawn(self, *, offer: Offer, application: Application) -> None:
        job_title = self._job_title(application)
        self._emit_offer_event(
            event_type=NotificationEventType.OFFER_WITHDRAWN,
            offer=offer,
            application=application,
            staff_title="Offer withdrawn",
            staff_message_template="{candidate} offer was withdrawn{job_clause}.",
            notify_candidate=True,
            candidate_title="Offer withdrawn",
            candidate_message=self._candidate_offer_withdrawn_message(job_title),
            staff_roles=NOTIFICATION_STAFF_ROLES,
            priority=NotificationPriority.HIGH,
        )

    def _emit_offer_event(
        self,
        *,
        event_type: NotificationEventType,
        offer: Offer,
        application: Application,
        staff_title: str,
        staff_message_template: str,
        notify_candidate: bool,
        candidate_title: str | None,
        candidate_message: str | None,
        staff_roles: frozenset[str],
        priority: NotificationPriority,
    ) -> None:
        job_title = self._job_title(application)
        candidate_name = self._candidate_name(application)
        job_clause = f" for {job_title}" if job_title else ""
        base_meta = {
            "event_type": event_type.value,
            "offer_id": str(offer.id),
            "offer_status": offer.status,
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "company_id": str(application.company_id),
            "job_title": job_title,
        }

        if notify_candidate and candidate_title and candidate_message:
            self._safe_create(
                NotificationCreate(
                    recipient_type=NotificationRecipientType.CANDIDATE,
                    recipient_id=application.candidate_id,
                    company_id=application.company_id,
                    category=NotificationCategory.OFFER,
                    priority=priority,
                    title=candidate_title,
                    message=candidate_message,
                    entity_type="offer",
                    entity_id=offer.id,
                    metadata=self._candidate_safe_metadata(base_meta),
                ),
                recipient_email=self._candidate_email(application),
                recipient_display_name=candidate_name,
            )

        staff_message = staff_message_template.format(
            candidate=candidate_name,
            job_clause=job_clause,
        )
        self._notify_staff(
            company_id=application.company_id,
            category=NotificationCategory.OFFER,
            title=staff_title,
            message=staff_message,
            entity_type="offer",
            entity_id=offer.id,
            metadata={
                **base_meta,
                "candidate_id": str(application.candidate_id),
                "candidate_name": candidate_name,
            },
            roles=staff_roles,
            priority=priority,
        )
        self._dispatch_webhook(
            company_id=application.company_id,
            event_type=event_type,
            data={
                "offer_id": str(offer.id),
                "offer_status": offer.status,
                "application_id": str(application.id),
                "job_id": str(application.job_id),
                "company_id": str(application.company_id),
                "candidate_id": str(application.candidate_id),
                "job_title": job_title,
                "status": offer.status,
            },
            entity_key=f"offer:{offer.id}:{event_type.value}",
        )

    def _notify_staff(
        self,
        *,
        company_id: UUID,
        category: NotificationCategory,
        title: str,
        message: str,
        entity_type: str,
        entity_id: UUID,
        metadata: dict[str, Any],
        roles: frozenset[str] = NOTIFICATION_STAFF_ROLES,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> None:
        members = self.member_repository.list_active_by_company_and_roles(company_id, roles)
        seen_user_ids: set[UUID] = set()
        for member in members:
            if member.user_id in seen_user_ids:
                continue
            seen_user_ids.add(member.user_id)
            self._safe_create(
                NotificationCreate(
                    recipient_type=NotificationRecipientType.USER,
                    recipient_id=member.user_id,
                    company_id=company_id,
                    category=category,
                    priority=priority,
                    title=title,
                    message=message,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metadata=dict(metadata),
                ),
                recipient_email=self._member_email(member),
                recipient_display_name=self._member_display_name(member),
            )

    def _dispatch_webhook(
        self,
        *,
        company_id: UUID,
        event_type: NotificationEventType,
        data: dict[str, Any],
        entity_key: str,
    ) -> None:
        if self.webhook_dispatcher is None:
            return
        try:
            self.webhook_dispatcher.dispatch(
                company_id=company_id,
                event_type=event_type,
                data=data,
                entity_key=entity_key,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue webhook delivery event=%s company_id=%s entity=%s",
                event_type.value,
                company_id,
                entity_key,
            )

    def _safe_create(
        self,
        payload: NotificationCreate,
        *,
        recipient_email: str | None = None,
        recipient_display_name: str | None = None,
    ) -> None:
        """Best-effort create (+ optional email) after domain commit — never raise."""
        try:
            created = self.notification_service.create_notification(payload)
        except Exception:
            logger.exception(
                "Failed to create notification event=%s entity=%s/%s recipient=%s/%s",
                (payload.metadata or {}).get("event_type"),
                payload.entity_type,
                payload.entity_id,
                payload.recipient_type,
                payload.recipient_id,
            )
            return

        try:
            self.email_orchestrator.enqueue_for_notification(
                notification=created,
                recipient_email=recipient_email,
                recipient_display_name=recipient_display_name,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue notification email event=%s notification_id=%s",
                (payload.metadata or {}).get("event_type"),
                created.id,
            )

    @staticmethod
    def _candidate_safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in metadata.items() if key in _CANDIDATE_SAFE_METADATA_KEYS}

    @staticmethod
    def _job_title(application: Application) -> str | None:
        job = getattr(application, "job", None)
        if job is None:
            return None
        title = getattr(job, "title", None)
        return str(title) if title else None

    @staticmethod
    def _candidate_name(application: Application) -> str:
        candidate = getattr(application, "candidate", None)
        if candidate is None:
            return "Candidate"
        name = getattr(candidate, "full_name", None)
        return str(name) if name else "Candidate"

    @staticmethod
    def _candidate_email(application: Application) -> str | None:
        candidate = getattr(application, "candidate", None)
        if candidate is None:
            return None
        email = getattr(candidate, "email", None)
        return str(email).strip() if email else None

    @staticmethod
    def _member_email(member: Any) -> str | None:
        user = getattr(member, "user", None)
        if user is None:
            return None
        email = getattr(user, "email", None)
        return str(email).strip() if email else None

    @staticmethod
    def _member_display_name(member: Any) -> str | None:
        user = getattr(member, "user", None)
        if user is None:
            return None
        name = getattr(user, "full_name", None)
        return str(name).strip() if name else None

    @staticmethod
    def _candidate_application_message(status: str, job_title: str | None) -> str:
        if job_title:
            return f"Your application for {job_title} is now {status}."
        return f"Your application status is now {status}."

    @staticmethod
    def _candidate_interview_scheduled_message(job_title: str | None) -> str:
        if job_title:
            return f"An interview has been scheduled for your {job_title} application."
        return "An interview has been scheduled for your application."

    @staticmethod
    def _candidate_interview_status_message(status_label: str, job_title: str | None) -> str:
        if job_title:
            return f"Your interview for {job_title} is now {status_label}."
        return f"Your interview status is now {status_label}."

    @staticmethod
    def _candidate_offer_approved_message(job_title: str | None) -> str:
        if job_title:
            return f"You have received an offer for {job_title}."
        return "You have received a job offer."

    @staticmethod
    def _candidate_offer_withdrawn_message(job_title: str | None) -> str:
        if job_title:
            return f"The offer for {job_title} has been withdrawn."
        return "Your offer has been withdrawn."
