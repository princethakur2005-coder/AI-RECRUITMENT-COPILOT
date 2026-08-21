"""Recipient notification channel preferences (default-driven)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.notification import NotificationRecipientType
from app.db.base import Base


class NotificationPreference(Base):
    """Per-recipient channel preferences.

    Default-driven: absence of a row means all configurable channels/categories
    are enabled. Staff rows are company-scoped; candidate rows have no company.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "recipient_type",
            "recipient_id",
            "company_id",
            name="uq_notification_preferences_recipient_company",
        ),
        Index(
            "ix_notification_preferences_recipient",
            "recipient_type",
            "recipient_id",
        ),
        Index(
            "uq_notification_preferences_candidate_recipient",
            "recipient_type",
            "recipient_id",
            unique=True,
            postgresql_where=text("company_id IS NULL"),
            sqlite_where=text("company_id IS NULL"),
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
    recipient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Category values excluded from the channel (SYSTEM never stored here).
    email_disabled_categories_json: Mapped[list[Any]] = mapped_column(
        "email_disabled_categories",
        JSON,
        nullable=False,
        default=list,
    )
    in_app_disabled_categories_json: Mapped[list[Any]] = mapped_column(
        "in_app_disabled_categories",
        JSON,
        nullable=False,
        default=list,
    )
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

    @property
    def email_disabled_categories(self) -> list[str]:
        return [str(item) for item in (self.email_disabled_categories_json or [])]

    @property
    def in_app_disabled_categories(self) -> list[str]:
        return [str(item) for item in (self.in_app_disabled_categories_json or [])]
