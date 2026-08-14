"""Interview ↔ calendar synchronization orchestration (durable-job backed)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.calendar import (
    CALENDAR_SYNC_SCHEDULE_FIELDS,
    CalendarSyncOperation,
    CalendarSyncStatus,
)
from app.core.durable_job import DurableJobType
from app.core.interview_status import InterviewStatus
from app.models.interview import Interview
from app.models.interview_calendar_sync import InterviewCalendarSync
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.schemas.calendar import CalendarAttendee, CalendarEventRequest
from app.schemas.durable_job import DurableJobSubmit
from app.services.durable_job_service import DurableJobService

logger = logging.getLogger("app.calendar_sync")


class CalendarSyncService:
    """Enqueues provider-neutral calendar sync jobs. Never performs HTTP itself."""

    def __init__(
        self,
        sync_repository: InterviewCalendarSyncRepository,
        integration_repository: CalendarIntegrationRepository,
        interview_repository: InterviewRepository,
        job_service: DurableJobService | None = None,
    ) -> None:
        self.sync_repository = sync_repository
        self.integration_repository = integration_repository
        self.interview_repository = interview_repository
        self.job_service = job_service

    def on_interview_scheduled(self, interview: Interview) -> None:
        self._enqueue(interview, CalendarSyncOperation.CREATE)

    def on_interview_updated(
        self,
        interview: Interview,
        *,
        changed_fields: set[str],
        previous_status: str | None = None,
    ) -> None:
        new_status = str(interview.status)
        if previous_status != new_status and new_status == InterviewStatus.CANCELLED.value:
            self._enqueue(interview, CalendarSyncOperation.CANCEL)
            return
        if CALENDAR_SYNC_SCHEDULE_FIELDS.intersection(changed_fields):
            sync = self.sync_repository.get_by_interview_id(interview.id)
            if sync is not None and sync.external_event_id:
                self._enqueue(interview, CalendarSyncOperation.UPDATE)
            else:
                self._enqueue(interview, CalendarSyncOperation.CREATE)

    def on_interview_cancelled(self, interview: Interview) -> None:
        self._enqueue(interview, CalendarSyncOperation.CANCEL)

    def on_interview_deleting(self, interview: Interview) -> None:
        """Enqueue cancel before hard-delete; snapshot external_event_id into job payload."""
        self._enqueue(interview, CalendarSyncOperation.CANCEL, allow_missing_after_delete=True)

    def build_event_request(
        self,
        interview: Interview,
        *,
        external_event_id: str | None = None,
        external_calendar_id: str | None = None,
    ) -> CalendarEventRequest:
        application = getattr(interview, "application", None)
        candidate = getattr(application, "candidate", None) if application else None
        job = getattr(application, "job", None) if application else None
        member = getattr(interview, "interviewer_member", None)
        interviewer_user = getattr(member, "user", None) if member else None

        job_title = getattr(job, "title", None) if job else None
        candidate_name = getattr(candidate, "full_name", None) if candidate else None
        title_bits = ["Interview"]
        if job_title:
            title_bits.append(f"— {job_title}")
        if candidate_name:
            title_bits.append(f"({candidate_name})")
        title = " ".join(title_bits)

        attendees: list[CalendarAttendee] = []
        if interviewer_user is not None and getattr(interviewer_user, "email", None):
            attendees.append(
                CalendarAttendee(
                    email=str(interviewer_user.email),
                    display_name=getattr(interviewer_user, "full_name", None),
                    role="interviewer",
                )
            )
        if candidate is not None and getattr(candidate, "email", None):
            attendees.append(
                CalendarAttendee(
                    email=str(candidate.email),
                    display_name=getattr(candidate, "full_name", None),
                    role="candidate",
                )
            )

        # Never put recruiter private notes into external calendar description.
        description_parts = []
        if job_title:
            description_parts.append(f"Role: {job_title}")
        description_parts.append(f"Interview type: {interview.interview_type}")

        return CalendarEventRequest(
            interview_id=interview.id,
            company_id=interview.company_id,
            title=title,
            description="\n".join(description_parts),
            start_at=interview.scheduled_start,
            end_at=interview.scheduled_end,
            timezone=interview.timezone,
            location=interview.location,
            meeting_link=interview.meeting_link,
            attendees=attendees,
            external_event_id=external_event_id,
            external_calendar_id=external_calendar_id,
            metadata={
                "application_id": str(interview.application_id),
                "interview_type": interview.interview_type,
                "interview_status": interview.status,
            },
        )

    def _enqueue(
        self,
        interview: Interview,
        operation: CalendarSyncOperation,
        *,
        allow_missing_after_delete: bool = False,
    ) -> None:
        try:
            integration = self.integration_repository.get_active_for_company(interview.company_id)
            if integration is None:
                sync = self.sync_repository.get_or_create_for_interview(
                    interview_id=interview.id,
                    company_id=interview.company_id,
                    calendar_integration_id=None,
                    sync_status=CalendarSyncStatus.NOT_CONNECTED.value,
                    commit=True,
                )
                self.sync_repository.update(
                    sync,
                    {
                        "sync_status": CalendarSyncStatus.NOT_CONNECTED.value,
                        "last_operation": operation.value,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                return

            sync = self.sync_repository.get_or_create_for_interview(
                interview_id=interview.id,
                company_id=interview.company_id,
                calendar_integration_id=integration.id,
                sync_status=CalendarSyncStatus.PENDING.value,
                commit=False,
            )
            updates: dict[str, Any] = {
                "calendar_integration_id": integration.id,
                "sync_status": CalendarSyncStatus.PENDING.value,
                "last_operation": operation.value,
                "last_error_code": None,
                "last_error_message": None,
                "updated_at": datetime.now(timezone.utc),
            }
            sync = self.sync_repository.update(sync, updates, commit=True)

            if self.job_service is None:
                logger.warning(
                    "calendar_sync_enqueue_skipped_no_job_service interview_id=%s operation=%s",
                    interview.id,
                    operation.value,
                )
                return

            fingerprint = self._fingerprint(interview, operation)
            payload: dict[str, Any] = {
                "interview_id": str(interview.id),
                "company_id": str(interview.company_id),
                "sync_id": str(sync.id),
                "operation": operation.value,
                "integration_id": str(integration.id),
            }
            # Snapshot for cancel-after-delete when interview row may vanish.
            if operation == CalendarSyncOperation.CANCEL and sync.external_event_id:
                payload["external_event_id"] = sync.external_event_id
            if allow_missing_after_delete:
                payload["allow_missing_interview"] = True

            self.job_service.submit(
                DurableJobSubmit(
                    job_type=DurableJobType.CALENDAR_SYNC,
                    payload=payload,
                    idempotency_key=f"calendar:{interview.id}:{operation.value}:{fingerprint}",
                    correlation_id=str(interview.id),
                    company_id=interview.company_id,
                )
            )
        except Exception:
            logger.exception(
                "calendar_sync_enqueue_failed interview_id=%s operation=%s",
                interview.id,
                operation.value,
            )

    @staticmethod
    def _fingerprint(interview: Interview, operation: CalendarSyncOperation) -> str:
        if operation == CalendarSyncOperation.CANCEL:
            return "cancel"
        start = interview.scheduled_start.isoformat() if interview.scheduled_start else ""
        end = interview.scheduled_end.isoformat() if interview.scheduled_end else ""
        updated = interview.updated_at.isoformat() if interview.updated_at else ""
        return f"{start}|{end}|{interview.timezone}|{interview.interviewer_member_id}|{updated}"
