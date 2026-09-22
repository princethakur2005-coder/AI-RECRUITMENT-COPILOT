from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.interview_status import DEFAULT_INTERVIEW_STATUS
from app.core.interview_type import DEFAULT_INTERVIEW_TYPE
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate import Candidate
    from app.models.company import Company
    from app.models.company_member import CompanyMember
    from app.models.interview_ai_analysis import InterviewAIAnalysis
    from app.models.job import Job


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
    candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    interviewer_member_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_members.id", ondelete="RESTRICT"),
        nullable=True,
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
    interview_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    questions_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
    candidate: Mapped["Candidate | None"] = relationship()
    job: Mapped["Job | None"] = relationship()
    interviewer_member: Mapped["CompanyMember | None"] = relationship(back_populates="interviews")
    ai_analysis: Mapped["InterviewAIAnalysis | None"] = relationship(
        back_populates="interview",
        uselist=False,
    )


class InterviewSession(Base):
    """Interview session containing role-based AI interview questions, candidate responses, and AI evaluations."""

    __tablename__ = "interview_sessions"
    __table_args__ = (
        Index("ix_interview_sessions_application_id", "application_id"),
        Index("ix_interview_sessions_candidate_id", "candidate_id"),
        Index("ix_interview_sessions_company_id", "company_id"),
        Index("ix_interview_sessions_job_id", "job_id"),
        Index("ix_interview_sessions_status", "status"),
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
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    interview_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    questions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    application: Mapped["Application"] = relationship(back_populates="interview_sessions")
    job: Mapped["Job"] = relationship()
    company: Mapped["Company"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
    interview: Mapped["Interview | None"] = relationship()
