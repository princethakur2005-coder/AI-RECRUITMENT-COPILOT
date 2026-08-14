from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.application import ApplicationCandidateSummary
from app.schemas.recommendation import (
    AIHiringSummary,
    DecisionConfidence,
    ExplainableDecisionReasons,
    HiringRecommendationPagination,
    RecruiterRecommendationMetadata,
    RiskFactor,
)


class RecruiterOverrideInfo(BaseModel):
    recommendation: str
    reason: str
    comment: str | None = None
    overridden_by_user_id: UUID
    overridden_at: datetime
    original_recommendation: str | None = None


class ApplicationHiringDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    recommendation: str
    overall_score: int = Field(ge=0, le=100)
    decision_confidence: DecisionConfidence
    strengths: list[str]
    weaknesses: list[str]
    missing_mandatory_qualifications: list[str]
    risk_factors: list[RiskFactor]
    reasons: ExplainableDecisionReasons
    recruiter_metadata: RecruiterRecommendationMetadata
    ai_hiring_summary: AIHiringSummary | None = None
    decision_detail: dict[str, Any] = Field(default_factory=dict)
    recruiter_override: RecruiterOverrideInfo | None = None
    policy_version: str
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False


class HiringDecisionOverrideRequest(BaseModel):
    recommendation: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    comment: str | None = None

    @model_validator(mode="after")
    def validate_recommendation_label(self) -> "HiringDecisionOverrideRequest":
        allowed = {"Strong Hire", "Hire", "Consider", "Reject"}
        label = str(self.recommendation or "").strip()
        if label not in allowed:
            raise ValueError(f"Invalid override recommendation '{self.recommendation}'. Allowed: {', '.join(sorted(allowed))}")
        self.recommendation = label
        return self


class JobHiringDecisionItemResponse(ApplicationHiringDecisionResponse):
    candidate_id: UUID
    job_id: UUID
    recommendation_position: int | None = Field(default=None, ge=1)
    candidate: ApplicationCandidateSummary | None = None


class JobHiringDecisionListResponse(BaseModel):
    job_id: UUID
    job_title: str | None = None
    items: list[JobHiringDecisionItemResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    generated_at: datetime
    pagination: HiringRecommendationPagination
    policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
