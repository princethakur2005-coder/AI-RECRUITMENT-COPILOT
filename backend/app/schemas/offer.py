from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompensationSummary(BaseModel):
    minimum: int | None = None
    maximum: int | None = None
    currency: str | None = Field(default=None, max_length=10)


class OfferHiringIntelligence(BaseModel):
    offer_status: str | None = None
    proposed_role: str | None = Field(default=None, max_length=255)
    compensation_summary: CompensationSummary | None = None
    start_date: datetime | None = None
    expiry_date: datetime | None = None
    approval_status: str | None = None


class OfferValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


class OfferValidationResult(BaseModel):
    is_valid: bool = True
    issues: list[OfferValidationIssue] = Field(default_factory=list)


class OfferBase(BaseModel):
    candidate_id: UUID
    job_id: UUID | None = None
    offer_title: str | None = Field(default=None, max_length=255)
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = Field(default=None, max_length=10)
    expires_at: datetime | None = None
    terms: str | None = None


class OfferCreate(OfferBase):
    pass


class OfferUpdate(BaseModel):
    offer_title: str | None = Field(default=None, max_length=255)
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = Field(default=None, max_length=10)
    expires_at: datetime | None = None
    terms: str | None = None
    status: str | None = Field(
        default=None,
        pattern="^(draft|pending_approval|approved|rejected|accepted|declined|expired|pending|withdrawn)$",
    )
    approved_by_id: UUID | None = None


class OfferResponse(OfferBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    job_id: UUID | None = None
    created_by_id: UUID | None = None
    approved_by_id: UUID | None = None
    status: str
    hiring_intelligence: OfferHiringIntelligence | None = None
    validation: OfferValidationResult | None = None
    created_at: datetime
    updated_at: datetime
