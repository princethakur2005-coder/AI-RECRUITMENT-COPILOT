from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.models.note import Note
from app.models.user import User
from app.repositories.note import NoteRepository
from app.services.audit_service import audit_service
from app.services.base import BaseService
from app.services.chat_service import ChatService
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER


class NoteService(BaseService[Note]):
    """Service layer for recruiter notes and AI-powered note suggestions."""

    def __init__(self, repository: NoteRepository, provider: Any | None = None) -> None:
        super().__init__(repository)
        self.repository = repository
        self.chat = ChatService(provider=provider, provider_name=getattr(provider, "provider_name", "gemini") if provider else "gemini")

    def create_note(self, note: Note, author: User | None = None) -> Note:
        created = super().create(note)
        audit_service.log(
            actor_id=str(author.id) if author else "system",
            actor_type="user" if author else "system",
            action="note_created",
            resource_type="candidate",
            resource_id=str(created.candidate_id),
            metadata={
                "note_id": str(created.id),
                "source": created.source,
                "pinned": created.pinned,
                "mentions": created.mentions,
            },
        )
        return created

    def update_note(self, db_obj: Note, obj_in: Dict[str, Any]) -> Note:
        updated = super().update(db_obj, obj_in)
        audit_service.log(
            actor_id=str(updated.author_id) if updated.author_id else "system",
            actor_type="user" if updated.author_id else "system",
            action="note_updated",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={
                "note_id": str(updated.id),
                "pinned": updated.pinned,
            },
        )
        return updated

    def list_candidate_notes(self, candidate_id: str) -> List[Note]:
        return self.repository.list_by_candidate(candidate_id)

    def list_pinned_notes(self, candidate_id: str) -> List[Note]:
        return self.repository.list_pinned_by_candidate(candidate_id)

    def generate_suggested_note(
        self,
        candidate: Dict[str, Any],
        recruiter_context: str | None = None,
        mention_user_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        candidate_summary = candidate.get("summary") or ""
        prompt = DEFAULT_PROMPT_MANAGER.render(
            "note_suggestion",
            candidate_name=candidate.get("full_name", "candidate"),
            candidate_summary=candidate_summary,
            recruiter_context=recruiter_context or "",
            mentions=", ".join(mention_user_ids or []),
        )
        prompt_text = prompt.get("prompt") if isinstance(prompt, dict) else str(prompt)
        resp = self.chat.send_message(prompt_text)
        suggested_content = resp.get("content", "")
        mentions = self._extract_mentions(suggested_content)
        return {
            "action": "suggest_note",
            "suggested_note": suggested_content,
            "mentions": mentions,
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }

    def _extract_mentions(self, content: str) -> List[str]:
        return [m.strip("@") for m in re.findall(r"@([A-Za-z0-9_\-]+)", content)]
