from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate import Candidate
    from app.models.company import Company
    from app.models.job import Job


class AssessmentSession(Base):
    """Assessment session containing role-based screening test questions, candidate responses, and scoring."""

    __tablename__ = "assessment_sessions"
    __table_args__ = (
        Index("ix_assessment_sessions_application_id", "application_id"),
        Index("ix_assessment_sessions_candidate_id", "candidate_id"),
        Index("ix_assessment_sessions_company_id", "company_id"),
        Index("ix_assessment_sessions_job_id", "job_id"),
        Index("ix_assessment_sessions_status", "status"),
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
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    questions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    breakdown_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    application: Mapped["Application"] = relationship(back_populates="assessment_sessions")
    job: Mapped["Job"] = relationship()
    company: Mapped["Company"] = relationship()
    candidate: Mapped["Candidate"] = relationship()
