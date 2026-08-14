from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class RecruiterSearchEntityType(StrEnum):
    CANDIDATE = "candidate"
    JOB = "job"
    APPLICATION = "application"


class RecruiterSearchHit(BaseModel):
    entity_type: RecruiterSearchEntityType
    entity_id: UUID
    title: str
    subtitle: str | None = None
    status: str | None = None
    job_id: UUID | None = None
    candidate_id: UUID | None = None
    application_id: UUID | None = None


class RecruiterSearchResponse(BaseModel):
    query: str
    items: list[RecruiterSearchHit] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 20
    candidate_total: int = 0
    job_total: int = 0
    application_total: int = 0
