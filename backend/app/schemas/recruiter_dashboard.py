from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.application_status import ApplicationStatus


class DashboardStatsResponse(BaseModel):
    total_jobs: int
    active_jobs: int
    open_jobs: int
    total_applications: int
    applied: int
    screening: int
    shortlisted: int
    interview: int
    offered: int
    hired: int
    rejected: int


class DashboardJobSummary(BaseModel):
    id: UUID
    title: str
    location: str | None
    department: str | None
    status: str
    application_count: int
    created_at: datetime


class DashboardJobListResponse(BaseModel):
    jobs: list[DashboardJobSummary]
    jobs_by_department: dict[str, int]


class DashboardCandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr


class DashboardJobRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str


class DashboardApplicationItem(BaseModel):
    id: UUID
    status: ApplicationStatus
    applied_at: datetime
    candidate: DashboardCandidateSummary | None = None
    job: DashboardJobRef | None = None


class DashboardRecentApplicationsResponse(BaseModel):
    applications: list[DashboardApplicationItem]


class DashboardPipelineGroup(BaseModel):
    status: ApplicationStatus
    count: int
    applications: list[DashboardApplicationItem]


class DashboardPipelineResponse(BaseModel):
    groups: list[DashboardPipelineGroup]


class DashboardOverviewResponse(BaseModel):
    stats: DashboardStatsResponse
    jobs_by_department: dict[str, int]
    applications_by_status: dict[str, int]
    generated_at: datetime


class DashboardUpcomingInterview(BaseModel):
    id: UUID
    application_id: UUID
    interview_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str
    status: str
    candidate_name: str | None = None
    job_title: str | None = None
    interviewer_name: str | None = None


class DashboardUpcomingInterviewsResponse(BaseModel):
    interviews: list[DashboardUpcomingInterview]
    interviews_today_count: int
