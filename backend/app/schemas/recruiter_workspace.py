from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RecruiterWorkspaceOverview(BaseModel):
    recruiter_id: str
    generated_at: datetime | str
    assigned_candidates_count: int = 0
    assigned_jobs_count: int = 0
    pending_interviews_count: int = 0
    pending_hiring_decisions_count: int = 0
    pending_offers_count: int = 0


class RecruiterWorkspaceListItem(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    status: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecruiterWorkspaceSummary(BaseModel):
    totals: dict[str, int] = Field(default_factory=dict)
    status_breakdown: dict[str, int] = Field(default_factory=dict)
    notification_summary: dict[str, Any] = Field(default_factory=dict)


class RecruiterWorkspaceResponse(BaseModel):
    overview: RecruiterWorkspaceOverview
    assigned_candidates: list[RecruiterWorkspaceListItem] = Field(default_factory=list)
    assigned_jobs: list[RecruiterWorkspaceListItem] = Field(default_factory=list)
    pending_interviews: list[RecruiterWorkspaceListItem] = Field(default_factory=list)
    pending_hiring_decisions: list[RecruiterWorkspaceListItem] = Field(default_factory=list)
    pending_offers: list[RecruiterWorkspaceListItem] = Field(default_factory=list)
    recent_recruiter_activities: list[dict[str, Any]] = Field(default_factory=list)
    workspace_summary: RecruiterWorkspaceSummary
