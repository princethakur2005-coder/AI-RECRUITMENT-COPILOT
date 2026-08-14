from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.interview_status import DEFAULT_INTERVIEW_STATUS
from app.core.interview_type import DEFAULT_INTERVIEW_TYPE
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.company import Company
    from app.models.company_member import CompanyMember
    from app.models.interview_ai_analysis import InterviewAIAnalysis


class Interview(Base):
    """Scheduled interview for a job application."""

    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_company_id_scheduled_start", "company_id", "scheduled_start"),
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
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interviewer_member_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_members.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    interview_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_INTERVIEW_TYPE,
        index=True,
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    meeting_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_INTERVIEW_STATUS,
        index=True,
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

    application: Mapped["Application"] = relationship(back_populates="interviews")
    company: Mapped["Company"] = relationship(back_populates="interviews")
    interviewer_member: Mapped["CompanyMember"] = relationship(back_populates="interviews")
    ai_analysis: Mapped["InterviewAIAnalysis | None"] = relationship(
        back_populates="interview",
        uselist=False,
    )
