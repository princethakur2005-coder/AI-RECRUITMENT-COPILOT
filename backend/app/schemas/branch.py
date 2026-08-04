from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BranchBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=100)


class BranchCreate(BranchBase):
    pass


class BranchResponse(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
