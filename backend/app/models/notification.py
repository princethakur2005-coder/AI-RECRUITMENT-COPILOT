from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.notification import (
    NotificationCategory,
    NotificationPriority,
    NotificationRecipientType,
    NotificationStatus,
)
from app.db.base import Base


class Notification(Base):
    """Persisted in-app notification for staff users or candidates.

    Authorization is recipient-scoped (and company-scoped for staff). This table
    is never an authorization source of truth for domain resources.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_created_at",
            "recipient_type",
            "recipient_id",
            "created_at",
        ),
        Index(
            "ix_notifications_company_recipient",
            "company_id",
            "recipient_type",
            "recipient_id",
        ),
        Index(
            "ix_notifications_recipient_status",
            "recipient_type",
            "recipient_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    recipient_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationRecipientType.USER.value,
    )
    recipient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=NotificationCategory.SYSTEM.value,
    )
    priority: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationPriority.NORMAL.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NotificationStatus.UNREAD.value,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
