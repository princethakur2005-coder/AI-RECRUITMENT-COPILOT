from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.application_status import PIPELINE_STATUSES
from app.models.application import Application
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.schemas.recruiter_dashboard import (
    DashboardApplicationItem,
    DashboardCandidateSummary,
    DashboardJobListResponse,
    DashboardJobRef,
    DashboardJobSummary,
    DashboardOverviewResponse,
    DashboardPipelineGroup,
    DashboardPipelineResponse,
    DashboardRecentApplicationsResponse,
    DashboardStatsResponse,
    DashboardUpcomingInterview,
    DashboardUpcomingInterviewsResponse,
)

DASHBOARD_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class RecruiterDashboardService:
    """Tenant-scoped recruiter workspace dashboard."""

    def __init__(
        self,
        job_repository: JobRepository,
        application_repository: ApplicationRepository,
        member_repository: CompanyMemberRepository,
        interview_repository: InterviewRepository | None = None,
    ) -> None:
        self.job_repository = job_repository
        self.application_repository = application_repository
        self.member_repository = member_repository
        self.interview_repository = interview_repository

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in DASHBOARD_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for recruiter workspace")
        return membership

    def _status_value(self, status_counts: dict[str, int], status: str) -> int:
        return int(status_counts.get(status, 0))

    def _to_application_item(self, application: Application) -> DashboardApplicationItem:
        candidate = application.candidate
        job = application.job
        candidate_summary = None
        if candidate is not None:
            candidate_summary = DashboardCandidateSummary(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
            )
        job_ref = None
        if job is not None:
            job_ref = DashboardJobRef(id=job.id, title=job.title)
        return DashboardApplicationItem(
            id=application.id,
            status=application.status,
            applied_at=application.applied_at,
            candidate=candidate_summary,
            job=job_ref,
        )

    def get_stats(self, user: User) -> DashboardStatsResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        job_counts = self.job_repository.get_job_counts(company_id)
        status_counts = self.application_repository.count_by_status(company_id)
        total_applications = self.application_repository.count_total(company_id)

        return DashboardStatsResponse(
            total_jobs=job_counts["total"],
            active_jobs=job_counts["active"],
            open_jobs=job_counts["open"],
            total_applications=total_applications,
            applied=self._status_value(status_counts, "applied"),
            screening=self._status_value(status_counts, "screening"),
            shortlisted=self._status_value(status_counts, "shortlisted"),
            interview=self._status_value(status_counts, "interview"),
            offered=self._status_value(status_counts, "offered"),
            hired=self._status_value(status_counts, "hired"),
            rejected=self._status_value(status_counts, "rejected"),
        )

    def get_jobs(self, user: User) -> DashboardJobListResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        rows = self.job_repository.list_with_application_counts(company_id)
        jobs = [
            DashboardJobSummary(
                id=row["id"],
                title=row["title"],
                location=row["location"],
                department=row["department"],
                status=row["status"],
                application_count=int(row["application_count"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
        jobs_by_department = self.job_repository.count_by_department(company_id)

        return DashboardJobListResponse(jobs=jobs, jobs_by_department=jobs_by_department)

    def get_pipeline(self, user: User) -> DashboardPipelineResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        applications = self.application_repository.list_for_dashboard(company_id)
        grouped: dict[str, list[Application]] = {status.value: [] for status in PIPELINE_STATUSES}
        for application in applications:
            grouped.setdefault(application.status, []).append(application)

        groups = [
            DashboardPipelineGroup(
                status=status,
                count=len(grouped.get(status.value, [])),
                applications=[
                    self._to_application_item(application)
                    for application in grouped.get(status.value, [])
                ],
            )
            for status in PIPELINE_STATUSES
        ]

        return DashboardPipelineResponse(groups=groups)

    def get_recent_applications(self, user: User) -> DashboardRecentApplicationsResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        applications = self.application_repository.list_recent_for_company(company_id, limit=20)
        return DashboardRecentApplicationsResponse(
            applications=[self._to_application_item(application) for application in applications],
        )

    def get_overview(self, user: User) -> DashboardOverviewResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        stats = self.get_stats(user)
        jobs_by_department = self.job_repository.count_by_department(company_id)
        status_counts = self.application_repository.count_by_status(company_id)

        return DashboardOverviewResponse(
            stats=stats,
            jobs_by_department=jobs_by_department,
            applications_by_status={status: int(count) for status, count in status_counts.items()},
            generated_at=datetime.now(timezone.utc),
        )

    def get_upcoming_interviews(self, user: User, limit: int = 10) -> DashboardUpcomingInterviewsResponse:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        if self.interview_repository is None:
            return DashboardUpcomingInterviewsResponse(interviews=[], interviews_today_count=0)

        interviews = self.interview_repository.list_upcoming_for_company(company_id, limit=limit)
        today_count = self.interview_repository.count_scheduled_today_for_company(company_id)

        items = []
        for interview in interviews:
            application = interview.application
            candidate_name = None
            job_title = None
            if application is not None:
                if application.candidate is not None:
                    candidate_name = application.candidate.full_name
                if application.job is not None:
                    job_title = application.job.title

            interviewer_name = None
            member = interview.interviewer_member
            if member is not None and member.user is not None:
                interviewer_name = member.user.full_name

            items.append(
                DashboardUpcomingInterview(
                    id=interview.id,
                    application_id=interview.application_id,
                    interview_type=interview.interview_type,
                    scheduled_start=interview.scheduled_start,
                    scheduled_end=interview.scheduled_end,
                    timezone=interview.timezone,
                    status=interview.status,
                    candidate_name=candidate_name,
                    job_title=job_title,
                    interviewer_name=interviewer_name,
                )
            )

        return DashboardUpcomingInterviewsResponse(
            interviews=items,
            interviews_today_count=today_count,
        )
