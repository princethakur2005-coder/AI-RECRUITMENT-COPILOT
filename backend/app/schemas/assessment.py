from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateAssessmentQuestion(BaseModel):
    """Question presented to candidate - answer keys strictly excluded."""

    id: str
    question: str
    options: dict[str, str]
    difficulty: str | None = None
    skill_tag: str | None = None


class CandidateAssessmentResponse(BaseModel):
    """Screening test retrieved by candidate."""

    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    application_id: UUID
    job_title: str | None = None
    status: str
    total_questions: int
    score: float | None = None
    questions: list[CandidateAssessmentQuestion] = Field(default_factory=list)
    completed_at: datetime | None = None


class CandidateAssessmentSubmitRequest(BaseModel):
    """Candidate submitted answers."""

    answers: dict[str, str] = Field(..., description="Mapping of question id to chosen option ('A', 'B', 'C', 'D')")


class QuestionBreakdownDetail(BaseModel):
    question_id: str
    question: str
    selected_option: str | None = None
    correct_option: str
    is_correct: bool
    explanation: str | None = None


class AssessmentBreakdown(BaseModel):
    score: float
    total_questions: int
    correct_count: int
    passed: bool
    details: list[QuestionBreakdownDetail] = Field(default_factory=list)


class CandidateAssessmentSubmitResponse(BaseModel):
    """Result returned upon successful assessment submission."""

    session_id: UUID
    application_id: UUID
    status: str
    score: float
    total_questions: int
    correct_count: int
    passed: bool
    breakdown: dict[str, Any]
    completed_at: datetime
