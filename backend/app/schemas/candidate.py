from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RecruiterNote(BaseModel):
    content: str
    author: str | None = None
    created_at: datetime
    updated_at: datetime


class CandidateTimelineEvent(BaseModel):
    event_type: str
    occurred_at: datetime
    content: str | None = None
    author: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateTimelineResponse(BaseModel):
    candidate_id: UUID
    events: list[CandidateTimelineEvent] = Field(default_factory=list)


class CandidateBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    experience_years: int | None = None
    skills: str | None = None
    summary: str | None = None
    resume_path: str | None = Field(default=None, max_length=500)
    linked_in: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    status: str = Field(default="new", max_length=50)
    is_active: bool = True


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    experience_years: int | None = None
    skills: str | None = None
    summary: str | None = None
    resume_path: str | None = Field(default=None, max_length=500)
    linked_in: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class CandidateResponse(CandidateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID | None = None
    application_id: UUID | None = None
    fit_score: float | None = None
    assessment_score: float | None = None
    assessment_breakdown: dict[str, Any] | None = None
    interview_score: float | None = None
    interview_feedback: dict[str, Any] | None = None
    composite_score: float | None = None
    hiring_decision: dict[str, Any] | None = None
    final_recommendation: str | None = None
    evaluation_summary: str | None = None
    ai_evaluation_summary: str | None = None
    recommendation_summary: str | None = None
    hiring_recommendation_summary: str | None = None
    resume_preview_url: str | None = None
    resume_url: str | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    candidate_match_summary: str | None = None
    recruiter_notes: list[RecruiterNote] = Field(default_factory=list)
    timeline: CandidateTimelineResponse | None = None
    created_at: datetime
    updated_at: datetime


class CandidateComparisonRequest(BaseModel):
    candidate_ids: list[UUID] = Field(..., min_length=2)
    job_description: str = Field(..., min_length=1)
    criteria: str | None = Field(default="skills, experience, culture fit")


class CandidateComparisonResponse(BaseModel):
    action: str
    recommendation: str
    provider: str
    status: str
    compared_candidates: list[dict[str, Any]] = Field(default_factory=list)
    comparative_strengths: dict[str, list[str]] = Field(default_factory=dict)
    comparative_weaknesses: dict[str, list[str]] = Field(default_factory=dict)
    skill_match_comparison: dict[str, Any] = Field(default_factory=dict)
    experience_comparison: dict[str, Any] = Field(default_factory=dict)
    education_comparison: dict[str, Any] = Field(default_factory=dict)
    hiring_recommendation_comparison: dict[str, Any] = Field(default_factory=dict)
    overall_comparison_summary: str | None = None
