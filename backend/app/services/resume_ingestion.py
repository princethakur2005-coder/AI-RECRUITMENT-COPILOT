from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.repositories.candidate import CandidateRepository
from app.services.candidate_profile import CandidateProfileGenerator
from app.services.duplicate_detection import DuplicateGuard
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.services.audit_service import audit_service
from app.services.event_bus import event_bus


@dataclass
class ResumeIngestionResult:
    candidate_id: str
    action: str
    duplicate_match: Optional[Dict[str, Any]]
    profile: Dict[str, Any]
    workflow_result: Dict[str, Any]
    candidate_record: Dict[str, Any]


class ResumeIngestionWorkflow:
    """Workflow for ingesting resumes into the candidate pipeline.

    This workflow detects duplicates, creates or updates candidate records,
    triggers AI parsing and profile generation, and publishes domain events.
    """

    def __init__(
        self,
        db: Session,
        repository: Optional[CandidateRepository] = None,
        profile_generator: Optional[CandidateProfileGenerator] = None,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        duplicate_guard: Optional[DuplicateGuard] = None,
    ) -> None:
        self.db = db
        self.repository = repository or CandidateRepository(db)
        self.profile_generator = profile_generator or CandidateProfileGenerator()
        self.orchestrator = orchestrator or WorkflowOrchestrator()
        self.duplicate_guard = duplicate_guard or DuplicateGuard()

    def ingest_resume(
        self,
        resume_text: str,
        uploaded_by_id: Optional[str] = None,
        candidate_email: Optional[str] = None,
        candidate_name: Optional[str] = None,
        candidate_phone: Optional[str] = None,
        job_id: Optional[str] = None,
        org_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResumeIngestionResult:
        """Ingest a resume, create or update the candidate, and trigger AI workflow."""
        profile_result = self.profile_generator.generate_profile(resume_text)
        profile = profile_result.get("profile") or {}

        candidate_email = candidate_email or profile.get("email")
        candidate_phone = candidate_phone or profile.get("phone")
        full_name = self._normalize_name(candidate_name or profile.get("full_name") or "")
        first_name, last_name = self._split_name(full_name)
        if not candidate_email:
            candidate_email = f"unknown-{uuid.uuid4()}@example.com"

        candidate_payload = {
            "first_name": first_name or "Unknown",
            "last_name": last_name or "Candidate",
            "full_name": full_name or f"Candidate {uuid.uuid4().hex[:8]}",
            "email": candidate_email,
            "phone": candidate_phone,
            "current_title": profile.get("current_title"),
            "location": profile.get("location"),
            "skills": self._serialize_skills(profile.get("technical_skills") or []),
            "summary": profile.get("summary"),
            "status": "new",
            "resume_path": None,
            "job_id": job_id,
            "created_by_id": uploaded_by_id,
        }

        duplicate_match = None
        candidate_record: Candidate
        action = "created"

        with self.db.begin():
            existing_by_email = None
            if candidate_email:
                existing_by_email = self.repository.get_by_email(candidate_email)

            existing_candidates = self.repository.get_all()
            existing_dicts = [self._candidate_to_dict(c) for c in existing_candidates]
            duplicate_match = self.duplicate_guard.find_duplicate_or_none({**candidate_payload, "resume_text": resume_text, "email": candidate_email}, existing_dicts)

            if existing_by_email is not None:
                duplicate_match = duplicate_match or {"existing_id": str(existing_by_email.id), "score": 1.0, "breakdown": {"email": 1.0}}

            if duplicate_match:
                candidate_record = existing_by_email if existing_by_email is not None else self.repository.get_by_email(candidate_email) or self.repository.get_by_email(candidate_email)
                if candidate_record is None and duplicate_match.get("existing_id"):
                    candidate_record = self.repository.get_by_id(duplicate_match["existing_id"])
                if candidate_record is None:
                    # unable to resolve an existing candidate, fallback to create new
                    candidate_record = self._create_candidate(candidate_payload)
                else:
                    candidate_record = self._update_candidate(candidate_record, candidate_payload)
                    action = "updated"
            else:
                candidate_record = self._create_candidate(candidate_payload)
                action = "created"

            self.duplicate_guard.record_new_candidate(str(candidate_record.id), resume_text)

        workflow_candidate = self._build_workflow_candidate(candidate_record, resume_text, profile_result)
        workflow_result = self.orchestrator.pipeline.parse_and_extract(workflow_candidate)

        event_payload = {
            "candidate_id": str(candidate_record.id),
            "org_id": org_id,
            "uploader_id": uploaded_by_id,
            "action": action,
            "duplicate": bool(duplicate_match),
            "duplicate_match": duplicate_match,
            "resume_text": resume_text,
            "metadata": metadata or {},
        }
        event_bus.publish("resume_uploaded", event_payload, background=True)

        audit_service.log(
            actor_id=uploaded_by_id or "system",
            actor_type="user" if uploaded_by_id else "system",
            action="resume_ingested",
            resource_type="candidate",
            resource_id=str(candidate_record.id),
            metadata={"action": action, "duplicate": bool(duplicate_match), "score": workflow_result.get("structured_resume", {}).get("raw_ai") is not None},
        )

        return ResumeIngestionResult(
            candidate_id=str(candidate_record.id),
            action=action,
            duplicate_match=duplicate_match,
            profile=profile_result,
            workflow_result=workflow_result,
            candidate_record=self._candidate_to_dict(candidate_record),
        )

    def _create_candidate(self, candidate_payload: Dict[str, Any]) -> Candidate:
        new_candidate = Candidate(**candidate_payload)
        return self.repository.create(new_candidate)

    def _update_candidate(self, candidate_record: Candidate, updates: Dict[str, Any]) -> Candidate:
        update_data = {k: v for k, v in updates.items() if v is not None and hasattr(candidate_record, k)}
        return self.repository.update(candidate_record, update_data)

    def _build_workflow_candidate(self, candidate_record: Candidate, resume_text: str, profile_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(candidate_record.id),
            "first_name": candidate_record.first_name,
            "last_name": candidate_record.last_name,
            "full_name": candidate_record.full_name,
            "email": candidate_record.email,
            "phone": candidate_record.phone,
            "resume_text": resume_text,
            "structured_resume": profile_result.get("raw_extraction") or {},
        }

    def _candidate_to_dict(self, candidate: Candidate) -> Dict[str, Any]:
        return {
            "id": str(candidate.id),
            "email": candidate.email,
            "phone": candidate.phone,
            "full_name": candidate.full_name,
            "current_title": candidate.current_title,
            "location": candidate.location,
            "skills": candidate.skills or "",
        }

    def _normalize_name(self, name: str) -> str:
        return " ".join(name.split()).strip()

    def _split_name(self, full_name: str) -> tuple[str, str]:
        parts = full_name.split()
        if not parts:
            return "Unknown", "Candidate"
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    def _serialize_skills(self, skills: List[str]) -> str:
        return ", ".join([s for s in skills if isinstance(s, str) and s.strip()])
