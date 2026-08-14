from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.core.notification import (
    NotificationCategory,
    NotificationPriority,
    NotificationRecipientType,
    NotificationStatus,
)


class NotificationCreate(BaseModel):
    """Internal create contract for producers (not a public write API yet)."""

    recipient_type: NotificationRecipientType
    recipient_id: UUID
    company_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    message: str = Field(..., min_length=1)
    category: NotificationCategory = NotificationCategory.SYSTEM
    priority: NotificationPriority = NotificationPriority.NORMAL
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_recipient_company_rules(self) -> "NotificationCreate":
        if self.recipient_type == NotificationRecipientType.USER and self.company_id is None:
            raise ValueError("company_id is required for staff (user) notifications")
        return self


class NotificationFilter(BaseModel):
    category: NotificationCategory | None = None
    priority: NotificationPriority | None = None
    status: NotificationStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class NotificationMarkReadRequest(BaseModel):
    """Supports both explicit status and frontend-compatible `read` flag."""

    status: NotificationStatus | None = None
    read: bool | None = None

    @model_validator(mode="after")
    def require_read_intent(self) -> "NotificationMarkReadRequest":
        if self.status is None and self.read is None:
            # Default PATCH body means mark as read.
            self.read = True
        if self.status is not None and self.status not in {
            NotificationStatus.READ,
            NotificationStatus.UNREAD,
        }:
            raise ValueError("status must be read or unread")
        return self

    @property
    def target_status(self) -> NotificationStatus:
        if self.status is not None:
            return self.status
        return NotificationStatus.READ if self.read else NotificationStatus.UNREAD


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recipient_type: NotificationRecipientType
    recipient_id: UUID
    company_id: UUID | None = None
    title: str | None = None
    message: str
    category: NotificationCategory
    priority: NotificationPriority
    status: NotificationStatus
    entity_type: str | None = None
    entity_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Compatibility aliases for the existing recruiter notifications UI contract.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def user_id(self) -> UUID | None:
        if self.recipient_type == NotificationRecipientType.USER:
            return self.recipient_id
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def read(self) -> bool:
        return self.status == NotificationStatus.READ

    @computed_field  # type: ignore[prop-decorator]
    @property
    def type(self) -> str:
        return self.category.value

    @classmethod
    def from_orm_notification(cls, row: Any) -> "NotificationResponse":
        metadata = getattr(row, "metadata_json", None)
        if metadata is None:
            metadata = getattr(row, "metadata", {}) or {}
        return cls(
            id=row.id,
            recipient_type=NotificationRecipientType(row.recipient_type),
            recipient_id=row.recipient_id,
            company_id=row.company_id,
            title=row.title,
            message=row.message,
            category=NotificationCategory(row.category),
            priority=NotificationPriority(row.priority),
            status=NotificationStatus(row.status),
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            metadata=dict(metadata or {}),
            read_at=row.read_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    total: int = 0
    unread_count: int = 0


class NotificationSummaryResponse(BaseModel):
    total: int = 0
    unread_count: int = 0
    read_count: int = 0


class NotificationMarkAllReadResponse(BaseModel):
    updated_count: int = 0
    unread_count: int = 0
