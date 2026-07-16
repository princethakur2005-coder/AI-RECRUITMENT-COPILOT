from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, validator


class NoteBase(BaseModel):
    candidate_id: UUID
    content: str = Field(..., min_length=1)
    source: str = Field(default="human", pattern="^(human|ai)$")
    pinned: bool = False
    mentions: list[str] | None = None

    @validator("mentions", pre=True, always=True)
    def normalize_mentions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    content: str | None = None
    pinned: bool | None = None
    mentions: list[str] | None = None

    @validator("mentions", pre=True, always=True)
    def normalize_mentions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class NoteResponse(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID | None
    created_at: datetime
    updated_at: datetime
