from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ActivityTimelineItem(BaseModel):
    id: str
    timestamp: datetime | str
    source: str = "activity_timeline"
    activity_type: str
    actor_id: str | None = None
    actor_type: str | None = None
    entity_type: str
    entity_id: str | None = None
    previous_state: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityTimelineCreate(BaseModel):
    activity_type: str
    actor_id: str | None = None
    actor_type: str | None = None
    entity_type: str
    entity_id: str | None = None
    timestamp: datetime | None = None
    previous_state: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityTimelineFilter(BaseModel):
    actor_id: str | None = None
    actor_type: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    activity_type: str | None = None
    source: str | None = None
    include_audit: bool = True
    include_notifications: bool = True
    include_manual: bool = True
    user_id: UUID | None = None
    since: str | None = None
    until: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ActivityTimelineListResponse(BaseModel):
    items: list[ActivityTimelineItem] = Field(default_factory=list)
    total: int = 0
