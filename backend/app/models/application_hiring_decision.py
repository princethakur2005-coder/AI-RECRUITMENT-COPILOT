from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application


class ApplicationHiringDecision(Base):
    """Persisted AI hiring decision for a single job application."""

    __tablename__ = "application_hiring_decisions"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_application_hiring_decisions_application"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_confidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_mandatory_qualifications: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    reasons: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recruiter_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ai_hiring_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decision_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recruiter_override: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
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

    application: Mapped["Application"] = relationship(back_populates="hiring_decision")
