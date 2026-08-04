from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    website: HttpUrl | str | None = None
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=100)


class CompanyCreate(CompanyBase):
    pass


class CompanyResponse(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    owner_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
