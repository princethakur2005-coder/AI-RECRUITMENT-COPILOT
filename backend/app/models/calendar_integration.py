"""Tenant-scoped external calendar connection configuration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.calendar import CalendarIntegrationStatus, CalendarProviderType
from app.db.base import Base


class CalendarIntegration(Base):
    """Company-owned calendar provider connection.

    Credentials are sealed at rest and never exposed via normal API responses
    or durable-job payloads. Interview remains the scheduling source of truth.
    """

    __tablename__ = "calendar_integrations"
    __table_args__ = (
        UniqueConstraint("company_id", "provider_type", name="uq_calendar_integrations_company_provider"),
        Index("ix_calendar_integrations_company_status", "company_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarProviderType.NULL.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarIntegrationStatus.ACTIVE.value,
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Sealed provider credentials JSON (OAuth tokens, etc.). Never log/return.
    credentials_sealed: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
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
