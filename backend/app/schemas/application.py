from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.application_status import ApplicationStatus


class ApplicationCreate(BaseModel):
    job_id: UUID
    candidate_id: UUID
    resume_path: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=100)


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationCandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    job_id: UUID
    candidate_id: UUID
    resume_path: str | None
    status: ApplicationStatus
    fit_score: float | None = None
    assessment_score: float | None = None
    interview_score: float | None = None
    composite_score: float | None = None
    hiring_decision_json: dict[str, Any] | None = None
    evaluation_summary: str | None = None
    ai_status: str = "pending"
    source: str | None
    applied_at: datetime
    updated_at: datetime


class ApplicationPipelineResponse(ApplicationResponse):
    candidate: ApplicationCandidateSummary | None = None
