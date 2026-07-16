from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DashboardOverview(BaseModel):
    total_candidates: int = 0
    total_jobs: int = 0
    interview_sessions: int = 0
    hired: int = 0
    generated_at: datetime | str


class CandidateMetrics(BaseModel):
    status_counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    recent_candidates: list[dict[str, Any]] = Field(default_factory=list)


class JobMetrics(BaseModel):
    status_counts: dict[str, int] = Field(default_factory=dict)
    jobs_by_department: dict[str, int] = Field(default_factory=dict)
    total: int = 0


class InterviewMetrics(BaseModel):
    interview_events: dict[str, int] = Field(default_factory=dict)
    average_interview_duration_minutes: float = 0.0
    interview_sessions: int = 0


class HiringMetrics(BaseModel):
    hired: int = 0
    rejected: int = 0
    offers_in_progress: int = 0
    interviews_in_progress: int = 0
    screening_in_progress: int = 0
    new_candidates: int = 0
    total_candidates: int = 0
    hire_rate: float = 0.0


class RecentActivitySummary(BaseModel):
    total_recent_activities: int = 0
    by_action: dict[str, int] = Field(default_factory=dict)
    by_entity_type: dict[str, int] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)


class NotificationSummary(BaseModel):
    total: int = 0
    unread: int = 0
    read: int = 0
    high_priority: int = 0


class DashboardResponse(BaseModel):
    overview: DashboardOverview
    candidate_metrics: CandidateMetrics
    job_metrics: JobMetrics
    interview_metrics: InterviewMetrics
    hiring_metrics: HiringMetrics
    recent_activity_summary: RecentActivitySummary
    notification_summary: NotificationSummary
    pipeline: dict[str, Any] = Field(default_factory=dict)
    funnel: dict[str, Any] = Field(default_factory=dict)
    job_statistics: dict[str, Any] = Field(default_factory=dict)
    recent_activity: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime | str
