from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogCreate(BaseModel):
    actor_id: str
    actor_type: str
    action: str
    entity_type: str
    entity_id: str | None = None
    previous_state: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str = "info"
    correlation_id: str | None = None


class AuditLogEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    timestamp: datetime | str
    actor_id: str | None = None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    previous_state: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str = "info"
    correlation_id: str | None = None
    company_id: UUID | None = None
    request_id: str | None = None
    created_at: datetime | None = None


class AuditLogFilter(BaseModel):
    actor_id: str | None = None
    actor_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    action: str | None = None
    level: str | None = None
    correlation_id: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int | None = Field(default=None, ge=1)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEvent] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
