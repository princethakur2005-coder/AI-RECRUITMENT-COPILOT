from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.offer_status import DEFAULT_OFFER_STATUS
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate import Candidate
    from app.models.job import Job
    from app.models.user import User


class Offer(Base):
    """Application-owned offer revision for the hiring lifecycle.

    Ownership source of truth is ``application_id``. Candidate/job are retained as
    denormalized references aligned to the linked Application. Company tenancy is
    derived through Application.company_id.
    """

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "revision",
            name="uq_offers_application_revision",
        ),
        Index(
            "uq_offers_one_active_per_application",
            "application_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE AND application_id IS NOT NULL"),
            sqlite_where=text("is_active IS 1 AND application_id IS NOT NULL"),
        ),
        Index(
            "ix_offers_application_id_created_at",
            "application_id",
            "created_at",
        ),
        Index(
            "ix_offers_is_active_status",
            "is_active",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    application_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supersedes_offer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("offers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )
    offer_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compensation_min: Mapped[int | None] = mapped_column(nullable=True)
    compensation_max: Mapped[int | None] = mapped_column(nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_OFFER_STATUS,
        server_default=text("'draft'"),
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

    application: Mapped["Application | None"] = relationship(back_populates="offers")
    candidate: Mapped["Candidate"] = relationship(back_populates="offers")
    job: Mapped["Job | None"] = relationship(back_populates="offers")
    created_by: Mapped["User | None"] = relationship(
        back_populates="created_offers",
        foreign_keys=[created_by_id],
    )
    approved_by: Mapped["User | None"] = relationship(
        back_populates="approved_offers",
        foreign_keys=[approved_by_id],
    )
    supersedes_offer: Mapped["Offer | None"] = relationship(
        remote_side=[id],
        foreign_keys=[supersedes_offer_id],
        uselist=False,
    )
