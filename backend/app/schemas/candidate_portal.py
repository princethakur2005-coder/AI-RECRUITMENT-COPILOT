"""Candidate-facing portal response contracts (least-privilege)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.application_status import ApplicationStatus
from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType
from app.core.offer_status import OfferStatus


class CandidateApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ApplicationStatus
    source: str | None = None
    applied_at: datetime
    updated_at: datetime
    job_id: UUID
    job_title: str | None = None
    company_id: UUID
    company_name: str | None = None
    assessment_score: float | None = None


class CandidateInterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    interview_type: InterviewType
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str
    meeting_link: str | None = None
    location: str | None = None
    status: InterviewStatus
    interviewer_name: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    created_at: datetime
    updated_at: datetime


class CandidateOfferResponse(BaseModel):
    """Candidate-visible offer fields only — no staff actor IDs or hiring intelligence."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID | None = None
    job_id: UUID | None = None
    revision: int = Field(ge=1)
    is_active: bool
    offer_title: str | None = None
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = None
    expires_at: datetime | None = None
    terms: str | None = None
    status: OfferStatus
    created_at: datetime
    updated_at: datetime
