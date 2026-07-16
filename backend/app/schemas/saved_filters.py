from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SavedFilterCategory(str, Enum):
    CANDIDATE = "candidate"
    JOB = "job"
    USER = "user"
    GLOBAL = "global"
    CUSTOM = "custom"


class SavedFilterCreate(BaseModel):
    owner_id: UUID | str
    name: str = Field(..., min_length=1, max_length=120)
    category: SavedFilterCategory = SavedFilterCategory.GLOBAL
    entity_type: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    query: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class SavedFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: SavedFilterCategory | None = None
    entity_type: str | None = None
    filters: dict[str, Any] | None = None
    query: str | None = None
    metadata: dict[str, Any] | None = None
    is_default: bool | None = None


class SavedFilterResponse(BaseModel):
    id: UUID
    owner_id: UUID | str
    name: str
    category: SavedFilterCategory
    entity_type: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    query: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class SavedFilterFilter(BaseModel):
    owner_id: UUID | str | None = None
    category: SavedFilterCategory | None = None
    entity_type: str | None = None
    is_default: bool | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SavedFilterListResponse(BaseModel):
    items: list[SavedFilterResponse] = Field(default_factory=list)
    total: int = 0
