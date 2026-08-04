from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.application_status import ApplicationStatus
from app.core.interview_status import DEFAULT_INTERVIEW_STATUS, InterviewStatus
from app.models.interview import Interview
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.schemas.interview import (
    InterviewApplicationSummary,
    InterviewCreate,
    InterviewInterviewerSummary,
    InterviewResponse,
    InterviewUpdate,
)

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
    ) -> None:
        self.interview_repository = interview_repository
        self.application_repository = application_repository
        self.member_repository = member_repository

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

        updates["updated_at"] = datetime.now(timezone.utc)
        updated = self.interview_repository.update(interview, updates)

        refreshed = self.interview_repository.get_by_id_for_company(updated.id, company_id)
        if refreshed is None:
            raise LookupError("Interview not found")
        return self._to_response(refreshed)

    def delete_interview(self, user: User, interview_id: UUID) -> None:
        membership = self._resolve_active_membership(user)
        interview = self.interview_repository.get_by_id_for_company(interview_id, membership.company_id)
        if not interview:
            raise LookupError("Interview not found")
        self.interview_repository.delete(interview)
