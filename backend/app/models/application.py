from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.application_status import DEFAULT_APPLICATION_STATUS
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application_ai_analysis import ApplicationAIAnalysis
    from app.models.application_hiring_decision import ApplicationHiringDecision
    from app.models.candidate import Candidate
    from app.models.company import Company
    from app.models.interview import Interview
    from app.models.job import Job
    from app.models.offer import Offer


class Application(Base):
    """Job application linking a candidate to a company job posting."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
        Index("ix_applications_company_id_applied_at", "company_id", "applied_at"),
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
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_APPLICATION_STATUS,
        index=True,
    )
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
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

    company: Mapped["Company"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    candidate: Mapped["Candidate"] = relationship(back_populates="applications")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="application")
    ai_analysis: Mapped["ApplicationAIAnalysis | None"] = relationship(
        back_populates="application",
        uselist=False,
    )
    hiring_decision: Mapped["ApplicationHiringDecision | None"] = relationship(
        back_populates="application",
        uselist=False,
    )
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )
