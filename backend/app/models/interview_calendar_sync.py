"""Per-interview calendar synchronization state (provider-neutral)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.calendar import CalendarSyncStatus
from app.db.base import Base


class InterviewCalendarSync(Base):
    """Maps an Interview to an external calendar event without polluting Interview.

    Interview status remains the recruitment workflow source of truth.
    """

    __tablename__ = "interview_calendar_syncs"
    __table_args__ = (
        UniqueConstraint("interview_id", name="uq_interview_calendar_syncs_interview_id"),
        Index("ix_interview_calendar_syncs_company_status", "company_id", "sync_status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    interview_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calendar_integration_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("calendar_integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sync_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarSyncStatus.NOT_CONNECTED.value,
        index=True,
    )
    # Provider-issued external event id — set once on create; never silently overwrite.
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_operation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
