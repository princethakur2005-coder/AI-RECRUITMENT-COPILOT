from __future__ import annotations

from pydantic import BaseModel, Field


class DecisionConfidence(BaseModel):
    overall: float = Field(..., ge=0.0, le=1.0)
    ranking_confidence: float = Field(..., ge=0.0, le=1.0)
    semantic_confidence: float = Field(..., ge=0.0, le=1.0)
    evaluation_confidence: float = Field(..., ge=0.0, le=1.0)


class ExplainableDecisionReasons(BaseModel):
    ranking_contribution: float = Field(..., ge=0.0, le=1.0)
    evaluation_contribution: float = Field(..., ge=0.0, le=1.0)
    semantic_contribution: float = Field(..., ge=0.0, le=1.0)
    risk_penalty: float = Field(..., ge=0.0, le=1.0)
    final_score: float = Field(..., ge=0.0, le=1.0)


class RecruiterRecommendationMetadata(BaseModel):
    summary: str
    next_step_hint: str
    ranking_position: int | None = None


class RiskFactor(BaseModel):
    code: str
    category: str
    severity: str
    message: str
    source: str


class AIHiringSummary(BaseModel):
    executive_summary: str
    hiring_recommendation_summary: str
    candidate_strengths: list[str] = Field(default_factory=list)
    candidate_concerns: list[str] = Field(default_factory=list)
    skill_gap_summary: str
    interview_highlights: list[str] = Field(default_factory=list)
    final_decision_rationale: str


class ExplainableDecision(BaseModel):
    recommendation: str
    overall_score: int = Field(..., ge=0, le=100)
    decision_confidence: DecisionConfidence
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_mandatory_qualifications: list[str] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    reasons: ExplainableDecisionReasons
    recruiter_metadata: RecruiterRecommendationMetadata
    ai_hiring_summary: AIHiringSummary | None = None


class HiringRecommendationItemResponse(ExplainableDecision):
    candidate_id: str
    job_id: str
    recommendation_position: int = Field(..., ge=1)


class HiringRecommendationPagination(BaseModel):
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
    pages: int = Field(..., ge=0)


class HiringRecommendationResponse(BaseModel):
    job_id: str
    job_title: str
    pagination: HiringRecommendationPagination
    items: list[HiringRecommendationItemResponse] = Field(default_factory=list)
