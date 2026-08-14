from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReportingScopeMeta(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None
    job_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    generated_at: datetime


class ReportingOverviewResponse(ReportingScopeMeta):
    total_jobs: int
    active_jobs: int
    total_applications: int
    applications_by_status: dict[str, int] = Field(default_factory=dict)
    interviews_scheduled: int
    interviews_completed: int
    offers_created: int
    offers_accepted: int
    hires: int


class ReportingPipelineResponse(ReportingScopeMeta):
    applications_by_status: dict[str, int] = Field(default_factory=dict)
    interviews_by_status: dict[str, int] = Field(default_factory=dict)
    offers_by_status: dict[str, int] = Field(default_factory=dict)


class TimeSeriesPoint(BaseModel):
    period: str
    count: int


class ReportingTimeSeriesResponse(ReportingScopeMeta):
    applications: list[TimeSeriesPoint] = Field(default_factory=list)
    interviews: list[TimeSeriesPoint] = Field(default_factory=list)
    hires: list[TimeSeriesPoint] = Field(default_factory=list)


class JobAnalyticsResponse(BaseModel):
    job_id: UUID
    company_id: UUID
    branch_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    generated_at: datetime
    applications: int
    interviews: int
    offers: int
    hires: int
    pipeline: dict[str, int] = Field(default_factory=dict)
