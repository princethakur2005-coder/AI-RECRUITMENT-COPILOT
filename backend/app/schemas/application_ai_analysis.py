from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationAIAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    overall_score: int = Field(ge=0, le=100)
    skills_score: int = Field(ge=0, le=100)
    experience_score: int = Field(ge=0, le=100)
    education_score: int = Field(ge=0, le=100)
    keyword_score: int = Field(ge=0, le=100)
    strengths: list[str]
    weaknesses: list[str]
    missing_skills: list[str]
    matched_skills: list[str]
    summary: str
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)
    ai_provider: str
    ai_model: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime
