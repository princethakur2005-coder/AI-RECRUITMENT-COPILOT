from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application import Application
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
    # Nullable so public Apply can create Candidate rows before portal account activation.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    applications: Mapped[list["Application"]] = relationship(back_populates="candidate")
    notes: Mapped[list["Note"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    offers: Mapped[list["Offer"]] = relationship(back_populates="candidate")

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

    @property
    def latest_application(self) -> Application | None:
        apps = self.applications or []
        if not apps:
            return None
        return sorted(
            apps,
            key=lambda a: getattr(a, "applied_at", None) or getattr(a, "created_at", None) or self.created_at,
            reverse=True,
        )[0]

    @property
    def application_id(self) -> UUID | None:
        app = self.latest_application
        return app.id if app is not None else None

    @property
    def fit_score(self) -> float | None:
        app = self.latest_application
        if app is not None:
            if app.fit_score is not None:
                return round(float(app.fit_score), 1)
            if app.ai_analysis is not None:
                return round(float(app.ai_analysis.overall_score), 1)
        return None

    @property
    def assessment_score(self) -> float | None:
        app = self.latest_application
        if app is not None and getattr(app, "assessment_score", None) is not None:
            return round(float(app.assessment_score), 1)
        return None

    @property
    def assessment_breakdown(self) -> dict[str, Any] | None:
        app = self.latest_application
        if app is not None:
            sessions = getattr(app, "assessment_sessions", None) or []
            completed = [s for s in sessions if getattr(s, "status", None) == "completed"]
            if completed:
                return completed[-1].breakdown_json
            if sessions and sessions[-1].breakdown_json:
                return sessions[-1].breakdown_json

            # Fallback to DB session lookup if in-memory relationship was not refreshed
            from sqlalchemy.orm import object_session
            sess = object_session(app) or object_session(self)
            if sess is not None:
                from app.models.assessment import AssessmentSession
                latest = (
                    sess.query(AssessmentSession)
                    .filter(
                        AssessmentSession.application_id == app.id,
                        AssessmentSession.status == "completed",
                    )
                    .order_by(AssessmentSession.created_at.desc())
                    .first()
                )
                if latest and latest.breakdown_json:
                    return latest.breakdown_json
        return None

    @property
    def interview_score(self) -> float | None:
        app = self.latest_application
        if app is not None and getattr(app, "interview_score", None) is not None:
            return round(float(app.interview_score), 1)
        return None

    @property
    def interview_feedback(self) -> dict[str, Any] | None:
        app = self.latest_application
        if app is not None:
            sessions = getattr(app, "interview_sessions", None) or []
            completed = [s for s in sessions if getattr(s, "status", None) == "completed"]
            if completed and completed[-1].evaluation_json:
                return completed[-1].evaluation_json
            if sessions and sessions[-1].evaluation_json:
                return sessions[-1].evaluation_json

            interviews = getattr(app, "interviews", None) or []
            for itv in reversed(interviews):
                if getattr(itv, "evaluation_json", None):
                    return itv.evaluation_json

            from sqlalchemy.orm import object_session
            sess = object_session(app) or object_session(self)
            if sess is not None:
                from app.models.interview import InterviewSession
                latest = (
                    sess.query(InterviewSession)
                    .filter(
                        InterviewSession.application_id == app.id,
                        InterviewSession.status == "completed",
                    )
                    .order_by(InterviewSession.created_at.desc())
                    .first()
                )
                if latest and latest.evaluation_json:
                    return latest.evaluation_json
        return None
    @property
    def composite_score(self) -> float | None:
        app = self.latest_application
        if app is not None and getattr(app, "composite_score", None) is not None:
            return round(float(app.composite_score), 1)
        return None

    @property
    def hiring_decision(self) -> dict[str, Any] | None:
        app = self.latest_application
        if app is not None and getattr(app, "hiring_decision_json", None) is not None:
            return app.hiring_decision_json
        return None

    @property
    def final_recommendation(self) -> str | None:
        dec = self.hiring_decision
        if dec and isinstance(dec, dict):
            return dec.get("recommendation")
        return None

    @property
    def evaluation_summary(self) -> str | None:
        app = self.latest_application
        if app is not None:
            if app.evaluation_summary:
                return app.evaluation_summary
            if app.ai_analysis is not None and app.ai_analysis.summary:
                return app.ai_analysis.summary
        return None

    @property
    def ai_evaluation_summary(self) -> str | None:
        return self.evaluation_summary

    @property
    def recommendation_summary(self) -> str | None:
        app = self.latest_application
        if app is not None and app.ai_analysis is not None:
            return app.ai_analysis.recommendation
        return None

    @property
    def hiring_recommendation_summary(self) -> str | None:
        return self.recommendation_summary

    @property
    def matched_skills(self) -> list[str]:
        app = self.latest_application
        if app is not None and app.ai_analysis is not None and app.ai_analysis.matched_skills:
            return list(app.ai_analysis.matched_skills)
        return []

    @property
    def missing_skills(self) -> list[str]:
        app = self.latest_application
        if app is not None and app.ai_analysis is not None and app.ai_analysis.missing_skills:
            return list(app.ai_analysis.missing_skills)
        return []

    @property
    def resume_preview_url(self) -> str | None:
        path = self.resume_path or (self.latest_application.resume_path if self.latest_application else None)
        if path:
            return f"/candidates/{self.id}/resume"
        return None

    @property
    def resume_url(self) -> str | None:
        return self.resume_preview_url

    @property
    def candidate_match_summary(self) -> str | None:
        if self.fit_score is not None:
            matched = self.matched_skills
            skills_part = f" Matched skills: {', '.join(matched)}." if matched else ""
            return f"Candidate match score: {int(self.fit_score)}%.{skills_part}"
        return None

