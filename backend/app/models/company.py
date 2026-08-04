from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.branch import Branch
    from app.models.company_member import CompanyMember
    from app.models.interview import Interview
    from app.models.job import Job
    from app.models.user import User


class Company(Base):
    """Tenant company profile for enterprise multi-tenancy."""

    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
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

    owner: Mapped["User"] = relationship(back_populates="owned_companies", foreign_keys=[owner_id])
    members: Mapped[list["User"]] = relationship(back_populates="company", foreign_keys="User.company_id")
    branches: Mapped[list["Branch"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    company_members: Mapped[list["CompanyMember"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")
    applications: Mapped[list["Application"]] = relationship(back_populates="company")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="company")
