from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InterviewPerformanceSignal(BaseModel):
    """Normalized interview performance payload for downstream evaluation engines."""

    interview_id: UUID
    application_id: UUID | None = None
    avg_score: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    avg_confidence: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    completion_ratio: float = Field(ge=0.0, le=1.0)


class InterviewAIAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interview_id: UUID
    overall_score: int = Field(ge=0, le=100)
    technical_score: int = Field(ge=0, le=100)
    communication_score: int = Field(ge=0, le=100)
    problem_solving_score: int = Field(ge=0, le=100)
    behavioral_score: int = Field(ge=0, le=100)
    strengths: list[str]
    weaknesses: list[str]
    gaps_identified: list[str]
    demonstrated_competencies: list[str]
    summary: str
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)
    ai_provider: str
    ai_model: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False
    performance_signal: InterviewPerformanceSignal | None = None
