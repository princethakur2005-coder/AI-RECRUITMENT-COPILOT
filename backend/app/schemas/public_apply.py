from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.application_status import ApplicationStatus


class PublicApplyForm(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)


class PublicApplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application_id: UUID
    job_id: UUID
    candidate_id: UUID
    status: ApplicationStatus
    applied_at: datetime
    message: str = "Application submitted successfully"


class PublicJobDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    department: str | None = None
    location: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    description: str | None = None
    requirements: list[str] = Field(default_factory=list)
    company_name: str | None = None
    status: str = "open"

