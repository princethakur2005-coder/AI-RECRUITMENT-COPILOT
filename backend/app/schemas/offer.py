from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.offer_status import OfferStatus
from app.schemas.application import ApplicationCandidateSummary


class CompensationSummary(BaseModel):
    minimum: int | None = None
    maximum: int | None = None
    currency: str | None = Field(default=None, max_length=10)


class OfferHiringIntelligence(BaseModel):
    offer_status: OfferStatus | None = None
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


class OfferWriteFields(BaseModel):
    """Mutable offer content fields shared by create/update flows."""

    offer_title: str | None = Field(default=None, max_length=255)
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = Field(default=None, max_length=10)
    expires_at: datetime | None = None
    terms: str | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None


class OfferCreate(OfferWriteFields):
    """Production create contract. Ownership is application-scoped."""

    application_id: UUID

    @model_validator(mode="after")
    def validate_required_create_fields(self) -> "OfferCreate":
        required = {
            "offer_title": self.offer_title,
            "compensation_min": self.compensation_min,
            "compensation_max": self.compensation_max,
            "currency": self.currency,
            "expires_at": self.expires_at,
        }
        missing = [name for name, value in required.items() if value in (None, "")]
        if missing:
            raise ValueError(f"Missing required offer fields: {', '.join(missing)}")
        return self


class OfferCreateForApplication(OfferWriteFields):
    """Nested application create body; application_id comes from the path."""

    @model_validator(mode="after")
    def validate_required_create_fields(self) -> "OfferCreateForApplication":
        required = {
            "offer_title": self.offer_title,
            "compensation_min": self.compensation_min,
            "compensation_max": self.compensation_max,
            "currency": self.currency,
            "expires_at": self.expires_at,
        }
        missing = [name for name, value in required.items() if value in (None, "")]
        if missing:
            raise ValueError(f"Missing required offer fields: {', '.join(missing)}")
        return self


class OfferUpdate(BaseModel):
    """Content-only updates. Status changes must use lifecycle endpoints."""

    offer_title: str | None = Field(default=None, max_length=255)
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = Field(default=None, max_length=10)
    expires_at: datetime | None = None
    terms: str | None = None


class OfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID | None = None
    candidate_id: UUID
    job_id: UUID | None = None
    created_by_id: UUID | None = None
    approved_by_id: UUID | None = None
    supersedes_offer_id: UUID | None = None
    revision: int = Field(ge=1)
    is_active: bool
    offer_title: str | None = None
    compensation_min: int | None = None
    compensation_max: int | None = None
    currency: str | None = None
    expires_at: datetime | None = None
    terms: str | None = None
    status: OfferStatus
    hiring_intelligence: OfferHiringIntelligence | None = None
    validation: OfferValidationResult | None = None
    created_at: datetime
    updated_at: datetime


class OfferPagination(BaseModel):
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
    pages: int = Field(..., ge=0)


class ApplicationOfferHistoryResponse(BaseModel):
    """Application-scoped current offer plus immutable revision history."""

    application_id: UUID
    current_offer: OfferResponse | None = None
    revisions: list[OfferResponse] = Field(default_factory=list)
    total_revisions: int = Field(ge=0)


class JobOfferItemResponse(OfferResponse):
    """Job-scoped offer row with application/candidate context for recruiter workflow."""

    application_status: str | None = None
    candidate: ApplicationCandidateSummary | None = None


class JobOfferListResponse(BaseModel):
    job_id: UUID
    items: list[JobOfferItemResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    generated_at: datetime
    pagination: OfferPagination
