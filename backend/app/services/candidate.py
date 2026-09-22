from __future__ import annotations

from uuid import UUID

from typing import Any, Dict

from app.models.candidate import Candidate
from app.models.note import Note
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateTimelineEvent, CandidateTimelineResponse
from app.schemas.note import NoteCreate, NoteUpdate
from app.services.audit_service import audit_service
from app.services.base import BaseService


class CandidateService(BaseService[Candidate]):
    """Service layer for candidate-related business operations."""

    def __init__(self, repository: CandidateRepository) -> None:
        super().__init__(repository)

    def create_candidate(self, candidate: Candidate) -> Candidate:
        created = super().create(candidate)
        audit_service.log(
            actor_id=str(created.created_by_id) if created.created_by_id else "system",
            actor_type="user" if created.created_by_id else "system",
            action="candidate_created",
            resource_type="candidate",
            resource_id=str(created.id),
            metadata={
                "email": created.email,
                "status": created.status,
            },
        )
        return created

    def get_candidate_by_email(self, email: str) -> Candidate | None:
        return self.repository.get_by_email(email)

    def update(self, db_obj: Candidate, obj_in: dict[str, Any]) -> Candidate:
        before: Dict[str, Any] = {field: getattr(db_obj, field, None) for field in obj_in.keys()}
        updated = super().update(db_obj, obj_in)
        if "status" in obj_in and updated.latest_application is not None:
            try:
                from datetime import datetime, timezone
                app = updated.latest_application
                status_val = str(obj_in["status"]).strip().lower()
                if status_val == "offer":
                    status_val = "offered"
                app.status = status_val
                app.updated_at = datetime.now(timezone.utc)
                if hasattr(self.repository, "session") and self.repository.session is not None:
                    self.repository.session.add(app)
                    self.repository.session.commit()
            except Exception:
                pass
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="candidate_updated",
            resource_type="candidate",
            resource_id=str(updated.id),
            metadata={
                "changes": {field: {"before": before.get(field), "after": obj_in.get(field)} for field in obj_in},
                "status": updated.status,
            },
        )
        return updated

    def delete(self, db_obj: Candidate) -> None:
        candidate_id = str(db_obj.id)
        metadata = {
            "email": db_obj.email,
            "status": db_obj.status,
        }
        super().delete(db_obj)
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="candidate_deleted",
            resource_type="candidate",
            resource_id=candidate_id,
            metadata=metadata,
        )

    def search_candidates_by_skill(self, skill: str) -> list[Candidate]:
        return self.repository.search_by_skill(skill)

    def search_candidates_by_status(self, status: str) -> list[Candidate]:
        return self.repository.search_by_status(status)

    def get_recruiter_notes(self, candidate: Candidate) -> list[dict[str, Any]]:
        return list(candidate.recruiter_notes)

    def get_candidate_timeline(self, candidate: Candidate) -> CandidateTimelineResponse:
        events = [CandidateTimelineEvent(**event) for event in candidate.candidate_timeline_events]
        events.sort(key=lambda item: item.occurred_at)
        return CandidateTimelineResponse(candidate_id=candidate.id, events=events)

    def add_recruiter_note(self, candidate: Candidate, note_in: NoteCreate, author_id: UUID | None = None) -> Candidate:
        note = Note(
            candidate_id=candidate.id,
            author_id=author_id,
            content=note_in.content,
            source=note_in.source,
            pinned=note_in.pinned,
            mentions=note_in.mentions,
        )
        candidate.notes.append(note)
        self.repository.db.add(candidate)
        self.repository.db.commit()
        self.repository.db.refresh(candidate)
        return candidate

    def update_recruiter_note(self, candidate: Candidate, note_id: UUID, note_in: NoteUpdate) -> Candidate:
        note = next((item for item in candidate.notes if item.id == note_id), None)
        if note is None:
            raise ValueError("Recruiter note not found")

        data = note_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(note, field, value)

        self.repository.db.add(note)
        self.repository.db.commit()
        self.repository.db.refresh(candidate)
        return candidate
