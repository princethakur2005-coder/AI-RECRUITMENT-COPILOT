from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.audit import AUDIT_ACTOR_USER, AuditAction, AuditResourceType
from app.core.application_status import ApplicationStatus
from app.core.interview_status import DEFAULT_INTERVIEW_STATUS, InterviewStatus
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.schemas.candidate_portal import CandidateInterviewResponse
from app.schemas.interview import (
    InterviewApplicationSummary,
    InterviewCreate,
    InterviewInterviewerSummary,
    InterviewResponse,
    InterviewUpdate,
)
from app.services.audit_service import emit_audit
from app.services.notification import NotificationService
from app.services.notification_factory import (
    build_calendar_sync_service,
    build_notification_event_producer,
)
from app.services.reporting_cache import invalidate_company_reporting_cache

logger = logging.getLogger("app.interview_management")

INTERVIEW_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})
BLOCKED_APPLICATION_STATUSES = frozenset({
    ApplicationStatus.HIRED,
    ApplicationStatus.REJECTED,
})


class InterviewService:
    """Tenant-scoped interview scheduling and management."""

    def __init__(
        self,
        interview_repository: InterviewRepository,
        application_repository: ApplicationRepository,
        member_repository: CompanyMemberRepository,
        notification_service: NotificationService | None = None,
        calendar_sync_service: Any | None = None,
    ) -> None:
        self.interview_repository = interview_repository
        self.application_repository = application_repository
        self.member_repository = member_repository
        _ = notification_service
        self.notification_events = build_notification_event_producer(interview_repository.db)
        self.calendar_sync = calendar_sync_service or build_calendar_sync_service(
            interview_repository.db
        )

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in INTERVIEW_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for interview management")
        return membership

    def _validate_schedule_window(self, scheduled_start: datetime, scheduled_end: datetime) -> None:
        if scheduled_end <= scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")

    def _validate_application_for_scheduling(self, application_status: str) -> None:
        if application_status in BLOCKED_APPLICATION_STATUSES:
            raise ValueError("Cannot schedule interviews for hired or rejected applications")

    def _to_response(self, interview: Interview) -> InterviewResponse:
        interviewer_summary = None
        member = interview.interviewer_member
        if member is not None and member.user is not None:
            interviewer_summary = InterviewInterviewerSummary(
                id=member.id,
                user_id=member.user_id,
                full_name=member.user.full_name,
                email=member.user.email,
                role=member.role,
            )

        application_summary = None
        application = interview.application
        if application is not None:
            candidate = application.candidate
            job = application.job
            application_summary = InterviewApplicationSummary(
                id=application.id,
                status=application.status,
                candidate_name=candidate.full_name if candidate else None,
                candidate_email=candidate.email if candidate else None,
                job_title=job.title if job else None,
            )

        return InterviewResponse(
            id=interview.id,
            application_id=interview.application_id,
            company_id=interview.company_id,
            interviewer_member_id=interview.interviewer_member_id,
            interview_type=interview.interview_type,
            scheduled_start=interview.scheduled_start,
            scheduled_end=interview.scheduled_end,
            timezone=interview.timezone,
            meeting_link=interview.meeting_link,
            location=interview.location,
            notes=interview.notes,
            status=interview.status,
            created_at=interview.created_at,
            updated_at=interview.updated_at,
            interviewer=interviewer_summary,
            application=application_summary,
        )

    def create_interview(self, user: User, payload: InterviewCreate) -> InterviewResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        application = self.application_repository.get_by_id_for_company(payload.application_id, company_id)
        if not application:
            raise LookupError("Application not found")

        self._validate_application_for_scheduling(application.status)
        self._validate_schedule_window(payload.scheduled_start, payload.scheduled_end)

        interviewer = self.member_repository.get_by_id_for_company(payload.interviewer_member_id, company_id)
        if not interviewer or not interviewer.is_active:
            raise LookupError("Interviewer not found")

        is_first_interview = self.interview_repository.count_by_application_id(application.id) == 0

        interview = Interview(
            application_id=application.id,
            company_id=company_id,
            interviewer_member_id=interviewer.id,
            interview_type=payload.interview_type,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            timezone=payload.timezone,
            meeting_link=payload.meeting_link,
            location=payload.location,
            notes=payload.notes,
            status=DEFAULT_INTERVIEW_STATUS,
        )
        created = self.interview_repository.create(interview)
        if is_first_interview and application.status == ApplicationStatus.SHORTLISTED:
            self.application_repository.update(
                application,
                {
                    "status": ApplicationStatus.INTERVIEW,
                    "updated_at": datetime.now(timezone.utc),
                },
            )

        refreshed = self.interview_repository.get_by_id_for_company(created.id, company_id)
        if refreshed is None:
            raise LookupError("Interview not found")
        if self.notification_events is not None:
            notify_application = self.application_repository.get_with_relations_for_company(
                application.id,
                company_id,
            )
            if notify_application is not None:
                self.notification_events.interview_scheduled(
                    interview=refreshed,
                    application=notify_application,
                )
        if self.calendar_sync is not None:
            try:
                self.calendar_sync.on_interview_scheduled(refreshed)
            except Exception:
                logger.exception(
                    "calendar_sync_on_schedule_failed interview_id=%s",
                    refreshed.id,
                )
        emit_audit(
            self.interview_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=user.id,
            action=AuditAction.INTERVIEW_CREATED.value,
            resource_type=AuditResourceType.INTERVIEW.value,
            resource_id=refreshed.id,
            metadata={
                "application_id": str(application.id),
                "interview_type": refreshed.interview_type,
                "status": refreshed.status,
                "application_status_advanced": bool(
                    is_first_interview and application.status == ApplicationStatus.INTERVIEW
                ),
            },
        )
        invalidate_company_reporting_cache(company_id)
        return self._to_response(refreshed)

    def get_interview(self, user: User, interview_id: UUID) -> InterviewResponse:
        membership = self._resolve_active_membership(user)
        interview = self.interview_repository.get_by_id_for_company(interview_id, membership.company_id)
        if not interview:
            raise LookupError("Interview not found")
        return self._to_response(interview)

    def list_interviews(self, user: User) -> list[InterviewResponse]:
        membership = self._resolve_active_membership(user)
        interviews = self.interview_repository.list_by_company_id(membership.company_id)
        return [self._to_response(item) for item in interviews]

    def list_interviews_for_application(self, user: User, application_id: UUID) -> list[InterviewResponse]:
        membership = self._resolve_active_membership(user)
        application = self.application_repository.get_by_id_for_company(application_id, membership.company_id)
        if not application:
            raise LookupError("Application not found")
        interviews = self.interview_repository.list_by_application_id(membership.company_id, application_id)
        return [self._to_response(item) for item in interviews]

    def list_upcoming_interviews(self, user: User, limit: int = 10) -> list[InterviewResponse]:
        membership = self._resolve_active_membership(user)
        interviews = self.interview_repository.list_upcoming_for_company(membership.company_id, limit=limit)
        return [self._to_response(item) for item in interviews]

    def count_interviews_today(self, user: User) -> int:
        membership = self._resolve_active_membership(user)
        return self.interview_repository.count_scheduled_today_for_company(membership.company_id)

    def update_interview(self, user: User, interview_id: UUID, payload: InterviewUpdate) -> InterviewResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        interview = self.interview_repository.get_by_id_for_company(interview_id, company_id)
        if not interview:
            raise LookupError("Interview not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return self._to_response(interview)

        application = self.application_repository.get_by_id_for_company(interview.application_id, company_id)
        if not application:
            raise LookupError("Application not found")

        new_start = updates.get("scheduled_start", interview.scheduled_start)
        new_end = updates.get("scheduled_end", interview.scheduled_end)
        self._validate_schedule_window(new_start, new_end)

        scheduling_fields = {"scheduled_start", "scheduled_end", "interviewer_member_id", "interview_type"}
        if scheduling_fields.intersection(updates.keys()) and interview.status == InterviewStatus.SCHEDULED:
            self._validate_application_for_scheduling(application.status)

        if "interviewer_member_id" in updates:
            interviewer = self.member_repository.get_by_id_for_company(updates["interviewer_member_id"], company_id)
            if not interviewer or not interviewer.is_active:
                raise LookupError("Interviewer not found")

        previous_status = interview.status
        raw_status = updates.get("status")
        if raw_status is not None:
            updates["status"] = (
                raw_status.value if isinstance(raw_status, InterviewStatus) else str(raw_status)
            )

        changed_fields = set(updates.keys()) - {"updated_at"}
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = self.interview_repository.update(interview, updates)

        refreshed = self.interview_repository.get_by_id_for_company(updated.id, company_id)
        if refreshed is None:
            raise LookupError("Interview not found")

        new_status = refreshed.status
        if (
            self.notification_events is not None
            and "status" in updates
            and previous_status != new_status
        ):
            notify_application = self.application_repository.get_with_relations_for_company(
                application.id,
                company_id,
            )
            if notify_application is not None:
                self.notification_events.interview_status_changed(
                    interview=refreshed,
                    application=notify_application,
                    previous_status=previous_status,
                    new_status=new_status,
                )
        if self.calendar_sync is not None:
            try:
                self.calendar_sync.on_interview_updated(
                    refreshed,
                    changed_fields=changed_fields,
                    previous_status=previous_status,
                )
            except Exception:
                logger.exception(
                    "calendar_sync_on_update_failed interview_id=%s",
                    refreshed.id,
                )
        emit_audit(
            self.interview_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=user.id,
            action=AuditAction.INTERVIEW_UPDATED.value,
            resource_type=AuditResourceType.INTERVIEW.value,
            resource_id=refreshed.id,
            metadata={
                "application_id": str(application.id),
                "changed_fields": sorted(changed_fields),
                "previous_status": previous_status,
                "status": refreshed.status,
            },
        )
        invalidate_company_reporting_cache(company_id)
        return self._to_response(refreshed)

    def delete_interview(self, user: User, interview_id: UUID) -> None:
        membership = self._resolve_active_membership(user)
        interview = self.interview_repository.get_by_id_for_company(interview_id, membership.company_id)
        if not interview:
            raise LookupError("Interview not found")
        application_id = interview.application_id
        company_id = membership.company_id
        if self.calendar_sync is not None:
            try:
                self.calendar_sync.on_interview_deleting(interview)
            except Exception:
                logger.exception(
                    "calendar_sync_on_delete_failed interview_id=%s",
                    interview.id,
                )
        self.interview_repository.delete(interview)
        emit_audit(
            self.interview_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=user.id,
            action=AuditAction.INTERVIEW_DELETED.value,
            resource_type=AuditResourceType.INTERVIEW.value,
            resource_id=interview_id,
            metadata={"application_id": str(application_id)},
        )
        invalidate_company_reporting_cache(company_id)

    def _to_candidate_response(self, interview: Interview) -> CandidateInterviewResponse:
        interviewer_name = None
        member = interview.interviewer_member
        if member is not None and member.user is not None:
            interviewer_name = member.user.full_name

        job_title = None
        company_name = None
        application = interview.application
        if application is not None and application.job is not None:
            job_title = application.job.title
        company = interview.company
        if company is not None:
            company_name = company.name
        elif application is not None and getattr(application, "company", None) is not None:
            company_name = application.company.name

        return CandidateInterviewResponse(
            id=interview.id,
            application_id=interview.application_id,
            interview_type=interview.interview_type,
            scheduled_start=interview.scheduled_start,
            scheduled_end=interview.scheduled_end,
            timezone=interview.timezone,
            meeting_link=interview.meeting_link,
            location=interview.location,
            status=interview.status,
            interviewer_name=interviewer_name,
            job_title=job_title,
            company_name=company_name,
            created_at=interview.created_at,
            updated_at=interview.updated_at,
        )

    def list_interviews_for_authenticated_candidate(
        self,
        candidate: Candidate,
    ) -> list[CandidateInterviewResponse]:
        interviews = self.interview_repository.list_owned_by_candidate(candidate.id)
        return [self._to_candidate_response(item) for item in interviews]

    def get_interview_for_authenticated_candidate(
        self,
        candidate: Candidate,
        interview_id: UUID,
    ) -> CandidateInterviewResponse:
        interview = self.interview_repository.get_owned_by_candidate(interview_id, candidate.id)
        if interview is None:
            raise LookupError("Interview not found")
        return self._to_candidate_response(interview)
