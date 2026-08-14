from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.application import ApplicationCandidateSummary, ApplicationPipelineResponse

AnalysisStatus = Literal["complete", "pending"]


class CandidateRankingItem(BaseModel):
    rank: int | None = None
    overall_rank_score: float | None = Field(default=None, ge=0.0, le=100.0)
    analysis_status: AnalysisStatus
    candidate: ApplicationCandidateSummary | None = None
    application: ApplicationPipelineResponse
    summary: str | None = None
    recommendation: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    skills_score: int | None = Field(default=None, ge=0, le=100)
    experience_score: int | None = Field(default=None, ge=0, le=100)
    overall_score: int | None = Field(default=None, ge=0, le=100)


class JobCandidateRankingResponse(BaseModel):
    job_id: UUID
    items: list[CandidateRankingItem]
    analyzed_count: int
    pending_count: int
    generated_at: datetime


class TopCandidateItem(BaseModel):
    rank: int
    overall_rank_score: float = Field(ge=0.0, le=100.0)
    candidate_name: str | None = None
    job_id: UUID
    job_title: str | None = None
    application_id: UUID
    recommendation: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_score: int | None = Field(default=None, ge=0, le=100)


class TopCandidatesResponse(BaseModel):
    candidates: list[TopCandidateItem]
    generated_at: datetime
