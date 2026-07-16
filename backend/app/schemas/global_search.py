from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SearchEntityType(str, Enum):
    CANDIDATE = "candidate"
    JOB = "job"
    USER = "user"


class GlobalSearchRequest(BaseModel):
    query: str = Field(default="")
    entity_types: list[SearchEntityType] = Field(
        default_factory=lambda: [
            SearchEntityType.CANDIDATE,
            SearchEntityType.JOB,
            SearchEntityType.USER,
        ]
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)
    filters: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class SearchPagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class SearchResultItem(BaseModel):
    entity_type: SearchEntityType
    entity_id: str
    title: str
    subtitle: str | None = None
    snippet: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SearchResultGroup(BaseModel):
    entity_type: SearchEntityType
    total: int = 0
    items: list[SearchResultItem] = Field(default_factory=list)


class GlobalSearchResponse(BaseModel):
    query: str
    items: list[SearchResultItem] = Field(default_factory=list)
    groups: list[SearchResultGroup] = Field(default_factory=list)
    pagination: SearchPagination
    metadata: dict[str, Any] = Field(default_factory=dict)
