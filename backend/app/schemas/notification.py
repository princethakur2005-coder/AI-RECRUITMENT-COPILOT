from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationCategory(str, Enum):
    SYSTEM = "system"
    CANDIDATE = "candidate"
    INTERVIEW = "interview"
    EVALUATION = "evaluation"
    RECOMMENDATION = "recommendation"
    OFFER = "offer"
    CUSTOM = "custom"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"


class NotificationHistoryEvent(BaseModel):
    event: str
    timestamp: datetime
    actor_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class NotificationCreate(BaseModel):
    user_id: UUID
    title: str | None = Field(default=None, max_length=255)
    message: str = Field(..., min_length=1)
    category: NotificationCategory = NotificationCategory.SYSTEM
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationFilter(BaseModel):
    user_id: UUID | None = None
    category: NotificationCategory | None = None
    priority: NotificationPriority | None = None
    status: NotificationStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str | None = None
    message: str
    category: NotificationCategory
    priority: NotificationPriority
    status: NotificationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    history: list[NotificationHistoryEvent] = Field(default_factory=list)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    total: int = 0
    unread_count: int = 0
