from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.offer_status import ACTIVE_OFFER_STATUSES, normalize_offer_status
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.offer import OfferRepository
from app.schemas.recruiter_workspace import (
    RecruiterWorkspaceListItem,
    RecruiterWorkspaceOverview,
    RecruiterWorkspaceResponse,
    RecruiterWorkspaceSummary,
)
from app.services.dashboard_service import DashboardService
from app.services.hiring_recommendation import HIRING_DECISION_ALLOWED_ROLES
from app.services.notification import NotificationService

HIRING_DECISION_QUEUE_STATUSES = frozenset({
    "decision_pending",
    "interview_completed",
    "final_review",
    "approval_pending",
})


class RecruiterWorkspaceService:
    """Read-only recruiter workspace aggregator built on existing services."""

    def __init__(
        self,
        db: Session,
        dashboard_service: DashboardService | None = None,
        notification_service: NotificationService | None = None,
        application_repository: ApplicationRepository | None = None,
        hiring_decision_repository: ApplicationHiringDecisionRepository | None = None,
        offer_repository: OfferRepository | None = None,
        member_repository: CompanyMemberRepository | None = None,
    ) -> None:
        self.db = db
        self.notification_service = notification_service
        self.dashboard_service = dashboard_service or DashboardService(
            db=db,
            notification_service=notification_service,
        )
        self.application_repository = application_repository or ApplicationRepository(db)
        self.hiring_decision_repository = hiring_decision_repository or ApplicationHiringDecisionRepository(db)
        self.offer_repository = offer_repository or OfferRepository(db)
        self.member_repository = member_repository or CompanyMemberRepository(db)

    def _resolve_hiring_decision_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in HIRING_DECISION_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for hiring decisions")
        return membership

    def get_workspace_for_user(self, user: User) -> RecruiterWorkspaceResponse:
        self._resolve_hiring_decision_membership(user)
        recruiter_id = str(user.id)
        assigned_candidates = self.get_assigned_candidates(recruiter_id=recruiter_id)
        assigned_jobs = self.get_assigned_jobs(recruiter_id=recruiter_id)
        pending_interviews = self.get_pending_interviews(recruiter_id=recruiter_id)
        pending_hiring_decisions = self.get_pending_hiring_decisions_for_user(user)
        pending_offers = self.get_pending_offers_for_user(user)
        recent_activities = self.get_recent_recruiter_activities(recruiter_id=recruiter_id)

        overview = RecruiterWorkspaceOverview(
            recruiter_id=recruiter_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
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
        decision_statuses = {status.lower() for status in HIRING_DECISION_QUEUE_STATUSES}
        return [item for item in candidates if str(item.status or "").lower() in decision_statuses]

    def get_pending_hiring_decisions_for_user(self, user: User) -> list[RecruiterWorkspaceListItem]:
        membership = self._resolve_hiring_decision_membership(user)
        company_id = membership.company_id
        applications = self.application_repository.list_by_company_id(company_id)
        items: list[RecruiterWorkspaceListItem] = []

        for application in applications:
            if str(application.status or "").lower() not in HIRING_DECISION_QUEUE_STATUSES:
                continue

            candidate = application.candidate
            decision = self.hiring_decision_repository.get_by_application_id_for_company(
                application.id,
                company_id,
            )
            metadata: dict[str, Any] = {
                "entity_type": "application",
                "application_id": str(application.id),
                "job_id": str(application.job_id),
                "candidate_id": str(application.candidate_id),
            }
            if decision is not None:
                metadata.update(
                    {
                        "decision_id": str(decision.id),
                        "recommendation": decision.recommendation,
                        "overall_score": decision.overall_score,
                        "policy_version": decision.policy_version,
                        "has_persisted_decision": True,
                    }
                )
            else:
                metadata["has_persisted_decision"] = False

            items.append(
                RecruiterWorkspaceListItem(
                    id=str(application.id),
                    title=candidate.full_name if candidate is not None else str(application.candidate_id),
                    subtitle=candidate.email if candidate is not None else None,
                    status=application.status,
                    created_at=self._to_iso_or_none(application.applied_at),
                    updated_at=self._to_iso_or_none(application.updated_at),
                    metadata=metadata,
                )
            )

        items.sort(
            key=lambda item: (
                0 if (item.metadata or {}).get("has_persisted_decision") else 1,
                str(item.updated_at or ""),
            ),
        )
        return items

    def get_pending_offers(self, recruiter_id: str) -> list[RecruiterWorkspaceListItem]:
        """Resolve pending offers via application-owned Offer data when membership is known."""
        try:
            user_id = UUID(str(recruiter_id))
        except (TypeError, ValueError):
            return []
        membership = self.member_repository.get_by_user_id(user_id)
        if membership is None or not membership.is_active:
            return []
        if membership.role not in HIRING_DECISION_ALLOWED_ROLES:
            return []
        return self._pending_offers_for_company(membership.company_id)

    def get_pending_offers_for_user(self, user: User) -> list[RecruiterWorkspaceListItem]:
        membership = self._resolve_hiring_decision_membership(user)
        return self._pending_offers_for_company(membership.company_id)

    def _pending_offers_for_company(self, company_id: UUID) -> list[RecruiterWorkspaceListItem]:
        """Authoritative pending queue from application-owned Offer lifecycle statuses."""
        pending_statuses = [status.value for status in ACTIVE_OFFER_STATUSES]
        offers = self.offer_repository.list_active_lifecycle_offers_for_company(
            company_id,
            statuses=pending_statuses,
        )
        items: list[RecruiterWorkspaceListItem] = []
        for offer in offers:
            try:
                if normalize_offer_status(offer.status) not in ACTIVE_OFFER_STATUSES:
                    continue
            except ValueError:
                continue

            application = offer.application
            if application is None or offer.application_id is None:
                continue
            candidate = application.candidate
            metadata: dict[str, Any] = {
                "entity_type": "offer",
                "offer_id": str(offer.id),
                "offer_status": offer.status,
                "offer_revision": offer.revision,
                "has_active_offer": True,
                "application_id": str(application.id),
                "application_status": application.status,
                "job_id": str(application.job_id),
                "candidate_id": str(application.candidate_id),
            }
            items.append(
                RecruiterWorkspaceListItem(
                    id=str(offer.id),
                    title=candidate.full_name if candidate is not None else str(application.candidate_id),
                    subtitle=candidate.email if candidate is not None else None,
                    status=offer.status,
                    created_at=self._to_iso_or_none(offer.created_at),
                    updated_at=self._to_iso_or_none(offer.updated_at),
                    metadata=metadata,
                )
            )

        items.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        return items

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
