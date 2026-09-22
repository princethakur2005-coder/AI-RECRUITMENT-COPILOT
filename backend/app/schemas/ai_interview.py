from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateInterviewQuestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    category: str
    competency: str
    difficulty: str | None = None
    context: str | None = None


class CandidateInterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    job_id: UUID
    job_title: str
    company_name: str
    status: str
    score: float | None = None
    questions: list[CandidateInterviewQuestion]
    evaluation: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CandidateInterviewSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(..., description="Mapping of question ID to candidate answer text")


class CandidateInterviewSubmitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interview_id: UUID | None = None
    session_id: UUID
    score: float
    status: str
    overall_feedback: str
    recommendation: str
    key_strengths: list[str] = Field(default_factory=list)
    growth_areas: list[str] = Field(default_factory=list)
    question_evaluations: list[dict[str, Any]] | None = None
