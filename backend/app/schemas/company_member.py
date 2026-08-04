from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

CompanyMemberRole = Literal["company_admin", "recruiter", "hiring_manager"]


class CompanyMemberCreate(BaseModel):
    user_id: UUID
    role: CompanyMemberRole
    branch_id: UUID | None = None


class CompanyMemberUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool


class CompanyMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    user_id: UUID
    branch_id: UUID | None
    role: str = Field(..., max_length=50)
    is_active: bool
    created_at: datetime
    updated_at: datetime
    user: CompanyMemberUserSummary
