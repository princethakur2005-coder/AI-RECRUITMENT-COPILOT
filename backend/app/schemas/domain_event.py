from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DomainEventPublish(BaseModel):
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class DomainEventResponse(BaseModel):
    id: str
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | str


class DomainEventSubscription(BaseModel):
    event_type: str
    handler_name: str


class DomainEventFilter(BaseModel):
    event_type: str | None = None
    source: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int | None = Field(default=None, ge=1)


class DomainEventListResponse(BaseModel):
    items: list[DomainEventResponse] = Field(default_factory=list)
    total: int = 0
