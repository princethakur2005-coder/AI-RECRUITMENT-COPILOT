from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.job import Job
    from app.models.note import Note
    from app.models.offer import Offer


class User(Base):
    """Application user account model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    jobs: Mapped[list["Job"]] = relationship(back_populates="created_by")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="created_by")
    notes: Mapped[list["Note"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    created_offers: Mapped[list["Offer"]] = relationship(back_populates="created_by", foreign_keys="Offer.created_by_id")
    approved_offers: Mapped[list["Offer"]] = relationship(back_populates="approved_by", foreign_keys="Offer.approved_by_id")
