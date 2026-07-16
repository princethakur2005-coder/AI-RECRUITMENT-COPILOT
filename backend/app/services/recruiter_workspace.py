from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.job import Job
from app.schemas.recruiter_workspace import (
    RecruiterWorkspaceListItem,
    RecruiterWorkspaceOverview,
    RecruiterWorkspaceResponse,
    RecruiterWorkspaceSummary,
)
from app.services.dashboard_service import DashboardService
from app.services.notification import NotificationService


class RecruiterWorkspaceService:
    """Read-only recruiter workspace aggregator built on existing services."""

    def __init__(
        self,
        db: Session,
        dashboard_service: DashboardService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.db = db
        self.notification_service = notification_service
        self.dashboard_service = dashboard_service or DashboardService(
            db=db,
            notification_service=notification_service,
        )

    def get_workspace(self, recruiter_id: str) -> RecruiterWorkspaceResponse:
        assigned_candidates = self.get_assigned_candidates(recruiter_id=recruiter_id)
        assigned_jobs = self.get_assigned_jobs(recruiter_id=recruiter_id)
        pending_interviews = self.get_pending_interviews(recruiter_id=recruiter_id)
        pending_hiring_decisions = self.get_pending_hiring_decisions(recruiter_id=recruiter_id)
        pending_offers = self.get_pending_offers(recruiter_id=recruiter_id)
        recent_activities = self.get_recent_recruiter_activities(recruiter_id=recruiter_id)

        overview = RecruiterWorkspaceOverview(
            recruiter_id=recruiter_id,
            generated_at=datetime.utcnow().isoformat() + "Z",
            assigned_candidates_count=len(assigned_candidates),
            assigned_jobs_count=len(assigned_jobs),
            pending_interviews_count=len(pending_interviews),
            pending_hiring_decisions_count=len(pending_hiring_decisions),
            pending_offers_count=len(pending_offers),
        )

        workspace_summary = self.get_workspace_summary(
            recruiter_id=recruiter_id,
            assigned_candidates=assigned_candidates,
            assigned_jobs=assigned_jobs,
            pending_interviews=pending_interviews,
            pending_hiring_decisions=pending_hiring_decisions,
            pending_offers=pending_offers,
        )

        return RecruiterWorkspaceResponse(
            overview=overview,
            assigned_candidates=assigned_candidates,
            assigned_jobs=assigned_jobs,
            pending_interviews=pending_interviews,
            pending_hiring_decisions=pending_hiring_decisions,
            pending_offers=pending_offers,
            recent_recruiter_activities=recent_activities,
            workspace_summary=workspace_summary,
        )

    def build_workspace(self, recruiter_id: str) -> RecruiterWorkspaceResponse:
        return self.get_workspace(recruiter_id=recruiter_id)

    def get_assigned_candidates(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        candidates = list(self.db.scalars(select(Candidate)).all())
        assigned: list[RecruiterWorkspaceListItem] = []
        for candidate in candidates:
            if not self._is_assigned_to_recruiter(candidate, recruiter_id):
                continue
            assigned.append(
                RecruiterWorkspaceListItem(
                    id=str(getattr(candidate, "id", "")),
                    title=str(getattr(candidate, "full_name", None) or getattr(candidate, "email", "Candidate")),
                    subtitle=getattr(candidate, "email", None),
                    status=getattr(candidate, "status", None),
                    created_at=self._to_iso_or_none(getattr(candidate, "created_at", None)),
                    updated_at=self._to_iso_or_none(getattr(candidate, "updated_at", None)),
                    metadata={
                        "job_id": self._to_str_or_none(getattr(candidate, "job_id", None)),
                    },
                )
            )
        return assigned

    def get_assigned_jobs(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        jobs = list(self.db.scalars(select(Job)).all())
        assigned: list[RecruiterWorkspaceListItem] = []
        for job in jobs:
            if not self._is_assigned_to_recruiter(job, recruiter_id):
                continue
            assigned.append(
                RecruiterWorkspaceListItem(
                    id=str(getattr(job, "id", "")),
                    title=str(getattr(job, "title", "Job")),
                    subtitle=getattr(job, "department", None),
                    status=getattr(job, "status", None),
                    created_at=self._to_iso_or_none(getattr(job, "created_at", None)),
                    updated_at=self._to_iso_or_none(getattr(job, "updated_at", None)),
                    metadata={},
                )
            )
        return assigned

    def get_pending_interviews(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        candidates = self.get_assigned_candidates(recruiter_id=recruiter_id)
        pending_statuses = {"interview", "interview_scheduled", "interview_pending", "onsite", "phone_screen"}
        return [item for item in candidates if str(item.status or "").lower() in pending_statuses]

    def get_pending_hiring_decisions(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        candidates = self.get_assigned_candidates(recruiter_id=recruiter_id)
        decision_statuses = {"decision_pending", "interview_completed", "final_review", "approval_pending"}
        return [item for item in candidates if str(item.status or "").lower() in decision_statuses]

    def get_pending_offers(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        candidates = self.get_assigned_candidates(recruiter_id=recruiter_id)
        offer_statuses = {"offer", "offer_pending", "offer_extended", "offer_approval_pending"}
        return [item for item in candidates if str(item.status or "").lower() in offer_statuses]

    def get_recent_recruiter_activities(self, recruiter_id: str, limit: int = 20) -> list[dict[str, Any]]:
        summary = self.dashboard_service.get_recent_activity_summary()
        activities = list(summary.get("items") or [])

        scoped: list[dict[str, Any]] = []
        for activity in activities:
            actor_id = str(activity.get("actor_id") or "")
            if actor_id and actor_id != recruiter_id:
                continue
            scoped.append(activity)

        scoped.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return scoped[:limit]

    def get_workspace_summary(
        self,
        recruiter_id: str,
        assigned_candidates: list[RecruiterWorkspaceListItem] | None = None,
        assigned_jobs: list[RecruiterWorkspaceListItem] | None = None,
        pending_interviews: list[RecruiterWorkspaceListItem] | None = None,
        pending_hiring_decisions: list[RecruiterWorkspaceListItem] | None = None,
        pending_offers: list[RecruiterWorkspaceListItem] | None = None,
    ) -> RecruiterWorkspaceSummary:
        candidate_items = assigned_candidates or self.get_assigned_candidates(recruiter_id=recruiter_id)
        job_items = assigned_jobs or self.get_assigned_jobs(recruiter_id=recruiter_id)
        interview_items = pending_interviews or self.get_pending_interviews(recruiter_id=recruiter_id)
        decision_items = pending_hiring_decisions or self.get_pending_hiring_decisions(recruiter_id=recruiter_id)
        offer_items = pending_offers or self.get_pending_offers(recruiter_id=recruiter_id)

        status_counter: Counter[str] = Counter()
        for item in candidate_items:
            status_counter[str(item.status or "unknown")] += 1

        notification_summary = self.dashboard_service.get_notification_summary()

        return RecruiterWorkspaceSummary(
            totals={
                "assigned_candidates": len(candidate_items),
                "assigned_jobs": len(job_items),
                "pending_interviews": len(interview_items),
                "pending_hiring_decisions": len(decision_items),
                "pending_offers": len(offer_items),
            },
            status_breakdown=dict(status_counter),
            notification_summary=notification_summary,
        )

    def _is_assigned_to_recruiter(self, obj: Any, recruiter_id: str) -> bool:
        candidate_fields = [
            "recruiter_id",
            "assigned_recruiter_id",
            "owner_id",
            "assignee_id",
            "created_by_id",
            "updated_by_id",
            "user_id",
        ]
        for field in candidate_fields:
            value = getattr(obj, field, None)
            if value is None:
                continue
            if str(value) == recruiter_id:
                return True
        return False

    def _to_iso_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _to_str_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


recruiter_workspace_service: RecruiterWorkspaceService | None = None
