from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.note import Note
    from app.models.offer import Offer
    from app.models.user import User


class RecruiterNotePayload(TypedDict):
    content: str
    author: str | None
    created_at: datetime
    updated_at: datetime


class CandidateTimelineEventPayload(TypedDict):
    event_type: str
    occurred_at: datetime
    content: str | None
    author: str | None
    metadata: dict[str, object]


class Candidate(Base):
    """ATS-oriented candidate profile model."""

    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id"),
        nullable=True,
        index=True,
    )
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    experience_years: Mapped[int | None] = mapped_column(nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linked_in: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new")
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

    created_by: Mapped["User | None"] = relationship(back_populates="candidates")
    job: Mapped["Job | None"] = relationship(back_populates="candidates")
    notes: Mapped[list["Note"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    offers: Mapped[list["Offer"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")

    @property
    def recruiter_notes(self) -> list[RecruiterNotePayload]:
        items: list[RecruiterNotePayload] = []
        for note in self.notes or []:
            author_obj = getattr(note, "author", None)
            author_name = None
            if author_obj is not None:
                author_name = getattr(author_obj, "full_name", None) or getattr(author_obj, "email", None)

            created_at = getattr(note, "created_at", None) or self.created_at
            updated_at = getattr(note, "updated_at", None) or created_at
            items.append(
                {
                    "content": str(getattr(note, "content", "") or ""),
                    "author": author_name,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )
        return items

    @property
    def candidate_timeline_events(self) -> list[CandidateTimelineEventPayload]:
        events: list[CandidateTimelineEventPayload] = []
        for note in self.notes or []:
            author_obj = getattr(note, "author", None)
            author_name = None
            if author_obj is not None:
                author_name = getattr(author_obj, "full_name", None) or getattr(author_obj, "email", None)

            occurred_at = getattr(note, "created_at", None) or self.created_at
            events.append(
                {
                    "event_type": "recruiter_note",
                    "occurred_at": occurred_at,
                    "content": str(getattr(note, "content", "") or ""),
                    "author": author_name,
                    "metadata": {
                        "note_id": str(getattr(note, "id", "") or ""),
                        "source": str(getattr(note, "source", "human") or "human"),
                        "pinned": bool(getattr(note, "pinned", False)),
                        "mentions": list(getattr(note, "mentions", []) or []),
                        "updated_at": getattr(note, "updated_at", None) or occurred_at,
                    },
                }
            )

        events.sort(key=lambda item: item["occurred_at"])
        return events
