from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.application_status import ApplicationStatus
from app.core.offer_status import (
    DEFAULT_OFFER_STATUS,
    OFFER_ELIGIBLE_RECOMMENDATIONS,
    OFFER_STATUSES,
    OfferStatus,
    TERMINAL_OFFER_STATUSES,
    normalize_offer_status,
    validate_offer_status_transition,
)
from app.models.application import Application
from app.models.application_hiring_decision import ApplicationHiringDecision
from app.models.candidate import Candidate
from app.models.offer import Offer
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.offer import OfferRepository
from app.schemas.offer import (
    ApplicationOfferHistoryResponse,
    JobOfferItemResponse,
    JobOfferListResponse,
    OfferCreate,
    OfferPagination,
    OfferResponse,
    OfferUpdate,
)
from app.schemas.application import ApplicationCandidateSummary
from app.schemas.candidate_portal import CandidateOfferResponse
from app.services.application import ApplicationService
from app.core.audit import AUDIT_ACTOR_CANDIDATE, AUDIT_ACTOR_USER
from app.services.audit_service import audit_service, emit_audit
from app.services.base import BaseService
from app.services.notification import NotificationService
from app.services.notification_factory import build_notification_event_producer
from app.services.reporting_cache import invalidate_company_reporting_cache

OFFER_READ_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})
OFFER_CREATE_ROLES = frozenset({"company_admin", "recruiter"})
OFFER_SUBMIT_ROLES = frozenset({"company_admin", "recruiter"})
OFFER_WITHDRAW_ROLES = frozenset({"company_admin", "recruiter"})
OFFER_APPROVE_ROLES = frozenset({"company_admin", "hiring_manager"})
OFFER_CONTENT_EDIT_ROLES = frozenset({"company_admin", "recruiter"})
TERMINAL_APPLICATION_STATUSES = frozenset({ApplicationStatus.HIRED, ApplicationStatus.REJECTED})
# In-flight offers that must be withdrawn before a new revision can be created.
BLOCKING_ACTIVE_OFFER_STATUSES = frozenset({OfferStatus.PENDING_APPROVAL, OfferStatus.APPROVED})

T = TypeVar("T")


class OfferService(BaseService[Offer]):
    """Production application-owned offer lifecycle with hiring-decision gating and RBAC."""

    VALID_STATUSES = {status.value for status in OFFER_STATUSES}

    def __init__(
        self,
        offer_repository: OfferRepository,
        application_repository: ApplicationRepository,
        member_repository: CompanyMemberRepository,
        hiring_decision_repository: ApplicationHiringDecisionRepository,
        application_service: ApplicationService,
        notification_service: NotificationService | None = None,
    ) -> None:
        super().__init__(offer_repository)
        self.offer_repository = offer_repository
        self.application_repository = application_repository
        self.member_repository = member_repository
        self.hiring_decision_repository = hiring_decision_repository
        self.application_service = application_service
        _ = notification_service
        self.notification_events = build_notification_event_producer(
            self.offer_repository.db,
        )

    def _db(self):
        return self.offer_repository.db

    def _run_transaction(self, work: Callable[[], T]) -> T:
        """Commit multi-entity offer/application mutations atomically."""
        try:
            result = work()
            self._db().commit()
            return result
        except Exception:
            self._db().rollback()
            raise

    def _resolve_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        return membership

    def _require_staff_role(self, user: User, allowed_roles: frozenset[str]):
        membership = self._resolve_membership(user)
        if membership.role not in allowed_roles:
            raise PermissionError("Insufficient permissions for this offer action")
        return membership

    def _get_application_for_company(self, application_id: UUID, company_id: UUID) -> Application:
        application = self.application_repository.get_by_id_for_company(application_id, company_id)
        if application is None:
            raise LookupError("Application not found")
        return application

    def _get_offer_for_company(self, offer_id: UUID, company_id: UUID) -> Offer:
        offer = self.offer_repository.get_by_id_for_company(offer_id, company_id)
        if offer is None:
            raise LookupError("Offer not found")
        return offer

    def _assert_application_not_terminal(self, application: Application) -> None:
        status = ApplicationStatus(application.status)
        if status in TERMINAL_APPLICATION_STATUSES:
            raise ValueError(f"Cannot manage offers for terminal application status '{status}'")

    def _effective_hiring_recommendation(self, decision: ApplicationHiringDecision) -> str:
        override = decision.recruiter_override
        if isinstance(override, dict):
            override_recommendation = override.get("recommendation")
            if override_recommendation:
                return str(override_recommendation).strip()
        return str(decision.recommendation or "").strip()

    def _assert_hiring_decision_gate(self, *, company_id: UUID, application_id: UUID) -> ApplicationHiringDecision:
        decision = self.hiring_decision_repository.get_by_application_id_for_company(
            application_id,
            company_id,
        )
        if decision is None:
            raise ValueError("Persisted hiring decision required before creating or submitting an offer")

        effective = self._effective_hiring_recommendation(decision)
        if effective not in OFFER_ELIGIBLE_RECOMMENDATIONS:
            raise ValueError(
                f"Hiring decision recommendation '{effective or 'unknown'}' is not eligible for offer creation"
            )
        return decision

    def _validate_create_payload(self, payload: OfferCreate, application: Application) -> None:
        if payload.candidate_id is not None and payload.candidate_id != application.candidate_id:
            raise ValueError("candidate_id does not match the application")
        if payload.job_id is not None and payload.job_id != application.job_id:
            raise ValueError("job_id does not match the application")

        required_field_values = {
            "offer_title": payload.offer_title,
            "compensation_min": payload.compensation_min,
            "compensation_max": payload.compensation_max,
            "currency": payload.currency,
            "expires_at": payload.expires_at,
        }
        missing_required = [field for field, value in required_field_values.items() if value in (None, "")]
        if missing_required:
            raise ValueError(f"Missing required offer fields: {', '.join(missing_required)}")

        if payload.compensation_min is not None and payload.compensation_min < 0:
            raise ValueError("compensation_min cannot be negative")
        if payload.compensation_max is not None and payload.compensation_max < 0:
            raise ValueError("compensation_max cannot be negative")
        if (
            payload.compensation_min is not None
            and payload.compensation_max is not None
            and payload.compensation_min > payload.compensation_max
        ):
            raise ValueError("compensation_min cannot be greater than compensation_max")
        if payload.expires_at is not None and payload.expires_at < datetime.now(timezone.utc):
            raise ValueError("expires_at cannot be in the past")

    def _to_response(self, offer: Offer) -> OfferResponse:
        return OfferResponse.model_validate(offer)

    def _offer_state_snapshot(self, offer: Offer) -> dict[str, Any]:
        return {
            "offer_id": str(offer.id),
            "status": offer.status,
            "revision": offer.revision,
            "is_active": offer.is_active,
            "application_id": str(offer.application_id) if offer.application_id else None,
            "supersedes_offer_id": str(offer.supersedes_offer_id) if offer.supersedes_offer_id else None,
        }

    def _audit_offer_event(
        self,
        *,
        action: str,
        offer: Offer,
        company_id: UUID,
        application: Application | None = None,
        previous_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        user: User | None = None,
        candidate: Candidate | None = None,
    ) -> None:
        if candidate is not None:
            actor_id = str(candidate.id)
            actor_type = AUDIT_ACTOR_CANDIDATE
        elif user is not None:
            actor_id = str(user.id)
            actor_type = AUDIT_ACTOR_USER
        else:
            raise ValueError("Offer audit requires a user or candidate actor")

        application_id = (
            str(application.id)
            if application is not None
            else (str(offer.application_id) if offer.application_id else None)
        )
        candidate_id = (
            str(application.candidate_id)
            if application is not None
            else str(offer.candidate_id)
        )
        job_id = (
            str(application.job_id)
            if application is not None
            else (str(offer.job_id) if offer.job_id else None)
        )
        event_metadata: dict[str, Any] = {
            "offer_id": str(offer.id),
            "application_id": application_id,
            "company_id": str(company_id),
            "candidate_id": candidate_id,
            "job_id": job_id,
            "revision": offer.revision,
            "status": offer.status,
            "is_active": offer.is_active,
        }
        if metadata:
            event_metadata.update(metadata)

        audit_service.log(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type="offer",
            resource_id=str(offer.id),
            entity_type="offer",
            entity_id=str(offer.id),
            previous_state=previous_state or {},
            current_state=self._offer_state_snapshot(offer),
            metadata=event_metadata,
        )
        emit_audit(
            self._db(),
            company_id=company_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type="offer",
            resource_id=offer.id,
            metadata=event_metadata,
            previous_state=previous_state or {},
            current_state=self._offer_state_snapshot(offer),
            write_jsonl=False,
        )

    def _to_job_offer_item(self, offer: Offer) -> JobOfferItemResponse:
        application = offer.application
        candidate_summary = None
        application_status = None
        if application is not None:
            application_status = application.status
            candidate = application.candidate
            if candidate is not None:
                candidate_summary = ApplicationCandidateSummary.model_validate(candidate)
        base = self._to_response(offer)
        return JobOfferItemResponse(
            **base.model_dump(),
            application_status=application_status,
            candidate=candidate_summary,
        )

    def _sync_application_status(
        self,
        *,
        company_id: UUID,
        application_id: UUID,
        target_status: ApplicationStatus,
        commit: bool = True,
    ) -> None:
        application = self._get_application_for_company(application_id, company_id)
        if application.status == target_status.value:
            return
        try:
            self.application_service.apply_status_transition(
                company_id=company_id,
                application_id=application_id,
                new_status=target_status.value,
                commit=commit,
            )
        except ValueError as exc:
            raise ValueError(f"Cannot synchronize application status to '{target_status}': {exc}") from exc

    def _release_application_from_offer_stage(
        self,
        *,
        company_id: UUID,
        application: Application,
        commit: bool = True,
    ) -> None:
        """When the current offer fails, return Application to INTERVIEW for a possible revision.

        Does not use terminal REJECTED — that remains for genuine application outcomes only.
        """
        if application.status != ApplicationStatus.OFFERED.value:
            return
        self._sync_application_status(
            company_id=company_id,
            application_id=application.id,
            target_status=ApplicationStatus.INTERVIEW,
            commit=commit,
        )

    def _require_active_offer(self, offer: Offer) -> None:
        if not offer.is_active:
            raise ValueError("Inactive or superseded offers cannot transition")
        if offer.application_id is None:
            raise ValueError("Offer is not linked to an application")
        status = normalize_offer_status(offer.status)
        if status in TERMINAL_OFFER_STATUSES:
            raise ValueError(f"Terminal offer status '{status}' cannot be modified")

    def _transition_active_offer(
        self,
        offer: Offer,
        new_status: OfferStatus,
        *,
        extra_updates: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Offer:
        self._require_active_offer(offer)
        validate_offer_status_transition(offer.status, new_status.value)
        updates: dict[str, Any] = {
            "status": new_status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if extra_updates:
            updates.update(extra_updates)
        return self.offer_repository.update(offer, updates, commit=commit)

    def _authorize_candidate_for_offer(self, candidate: Candidate, offer: Offer) -> UUID:
        """Authorize candidate-facing actions via authenticated Candidate → Application → Offer.

        Identity must already be the verified JWT candidate principal. Client-supplied
        email/candidate_id/company_id are never trusted here.
        """
        if offer.application_id is None:
            raise LookupError("Offer not found")

        company_id = self._company_id_for_offer(offer)
        application = self.application_repository.get_with_relations_for_company(
            offer.application_id,
            company_id,
        )
        if application is None:
            raise LookupError("Offer not found")
        if application.candidate_id != candidate.id:
            # Avoid leaking offer existence across candidate identities/tenants.
            raise LookupError("Offer not found")
        return company_id

    def _company_id_for_offer(self, offer: Offer) -> UUID:
        if offer.application is not None and getattr(offer.application, "company_id", None) is not None:
            return offer.application.company_id
        if offer.application_id is None:
            raise LookupError("Offer is not linked to an application")
        application = self.application_repository.get_by_id(offer.application_id)
        if application is None:
            raise LookupError("Application not found")
        return application.company_id

    def _supersede_active_offer(self, active: Offer) -> None:
        """Mark the previous revision immutable history before activating a new one."""
        self.offer_repository.update(
            active,
            {
                "is_active": False,
                "updated_at": datetime.now(timezone.utc),
            },
            commit=False,
        )

    def _transition_failed_offer(
        self,
        offer: Offer,
        new_status: OfferStatus,
        *,
        commit: bool = True,
    ) -> Offer:
        """Move offer to a failed terminal status and clear the active slot for a revision."""
        updated = self._transition_active_offer(offer, new_status, commit=False)
        updated = self.offer_repository.update(
            updated,
            {
                "is_active": False,
                "updated_at": datetime.now(timezone.utc),
            },
            commit=commit,
        )
        return updated

    def create_offer_for_application(
        self,
        user: User,
        application_id: UUID,
        payload: OfferCreate,
    ) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_CREATE_ROLES)
        company_id = membership.company_id
        application = self._get_application_for_company(application_id, company_id)
        self._assert_application_not_terminal(application)
        self._assert_hiring_decision_gate(company_id=company_id, application_id=application.id)

        if payload.application_id is not None and payload.application_id != application_id:
            raise ValueError("application_id in payload does not match path application")

        create_payload = payload.model_copy(update={"application_id": application_id})
        self._validate_create_payload(create_payload, application)

        active = self.offer_repository.get_active_by_application_id_for_company(
            company_id,
            application.id,
        )
        if active is not None:
            active_status = normalize_offer_status(active.status)
            if active_status in BLOCKING_ACTIVE_OFFER_STATUSES:
                raise ValueError(
                    "An active offer already exists for this application; "
                    "withdraw or complete it before creating a new revision"
                )

        latest = self.offer_repository.get_latest_by_application_id_for_company(
            company_id,
            application.id,
        )
        revision = self.offer_repository.next_revision_for_application(application.id)
        if active is not None:
            supersedes_offer_id = active.id
        elif latest is not None:
            supersedes_offer_id = latest.id
        else:
            supersedes_offer_id = None

        superseded_snapshot: dict[str, Any] | None = None
        superseded_offer_id: UUID | None = None

        def _create() -> Offer:
            nonlocal superseded_snapshot, superseded_offer_id
            if active is not None:
                superseded_snapshot = self._offer_state_snapshot(active)
                superseded_offer_id = active.id
                self._supersede_active_offer(active)

            offer = Offer(
                application_id=application.id,
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                created_by_id=user.id,
                supersedes_offer_id=supersedes_offer_id,
                revision=revision,
                is_active=True,
                offer_title=create_payload.offer_title,
                compensation_min=create_payload.compensation_min,
                compensation_max=create_payload.compensation_max,
                currency=create_payload.currency,
                expires_at=create_payload.expires_at,
                terms=create_payload.terms,
                status=str(DEFAULT_OFFER_STATUS),
            )
            return self.offer_repository.create(offer, commit=False)

        try:
            created = self._run_transaction(_create)
        except IntegrityError as exc:
            # Partial unique (one active) and (application_id, revision) protect concurrent creates.
            raise ValueError(
                "Could not create offer revision due to a concurrent update; refresh and retry"
            ) from exc
        self._db().refresh(created)
        if superseded_snapshot is not None and superseded_offer_id is not None and active is not None:
            self._audit_offer_event(
                user=user,
                action="offer_superseded",
                offer=active,
                company_id=company_id,
                application=application,
                previous_state=superseded_snapshot,
                metadata={
                    "superseded_by_offer_id": str(created.id),
                    "superseded_by_revision": created.revision,
                    "reason": "revised",
                },
            )
        action = "offer_revised" if supersedes_offer_id is not None else "offer_created"
        self._audit_offer_event(
            user=user,
            action=action,
            offer=created,
            company_id=company_id,
            application=application,
            metadata={
                "supersedes_offer_id": str(supersedes_offer_id) if supersedes_offer_id else None,
            },
        )
        if self.notification_events is not None:
            self.notification_events.offer_created(offer=created, application=application)
        invalidate_company_reporting_cache(company_id)
        return self._to_response(created)

    def create_offer(self, user: User, payload: OfferCreate) -> OfferResponse:
        if payload.application_id is None:
            raise ValueError("application_id is required")
        return self.create_offer_for_application(user, payload.application_id, payload)

    def list_offers_for_application(
        self,
        user: User,
        application_id: UUID,
        *,
        active_only: bool = False,
    ) -> list[OfferResponse]:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        self._get_application_for_company(application_id, membership.company_id)
        offers = self.offer_repository.list_by_application_id_for_company(
            membership.company_id,
            application_id,
            active_only=active_only,
        )
        return [self._to_response(offer) for offer in offers]

    def get_application_offer_history(
        self,
        user: User,
        application_id: UUID,
    ) -> ApplicationOfferHistoryResponse:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        self._get_application_for_company(application_id, membership.company_id)
        revisions = self.offer_repository.list_by_application_id_for_company(
            membership.company_id,
            application_id,
            active_only=False,
        )
        current = next((offer for offer in revisions if offer.is_active), None)
        if current is None:
            current = self.offer_repository.get_active_by_application_id_for_company(
                membership.company_id,
                application_id,
            )
        return ApplicationOfferHistoryResponse(
            application_id=application_id,
            current_offer=self._to_response(current) if current is not None else None,
            revisions=[self._to_response(offer) for offer in revisions],
            total_revisions=len(revisions),
        )

    def get_active_offer_for_application(
        self,
        user: User,
        application_id: UUID,
    ) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        self._get_application_for_company(application_id, membership.company_id)
        offer = self.offer_repository.get_active_by_application_id_for_company(
            membership.company_id,
            application_id,
        )
        if offer is None:
            raise LookupError("Active offer not found")
        return self._to_response(offer)

    def get_current_offer_for_application(
        self,
        user: User,
        application_id: UUID,
    ) -> OfferResponse:
        """Alias for the unambiguous current/active application-owned offer."""
        return self.get_active_offer_for_application(user, application_id)

    def get_offer(self, user: User, offer_id: UUID) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        return self._to_response(offer)

    def list_offers_for_candidate(self, user: User, candidate_id: UUID) -> list[OfferResponse]:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        offers = self.offer_repository.list_by_candidate_id_for_company(
            membership.company_id,
            candidate_id,
        )
        # Production reads only include application-owned offers.
        return [
            self._to_response(offer)
            for offer in offers
            if offer.application_id is not None
        ]

    def _to_candidate_offer_response(self, offer: Offer) -> CandidateOfferResponse:
        return CandidateOfferResponse(
            id=offer.id,
            application_id=offer.application_id,
            job_id=offer.job_id,
            revision=offer.revision,
            is_active=offer.is_active,
            offer_title=offer.offer_title,
            compensation_min=offer.compensation_min,
            compensation_max=offer.compensation_max,
            currency=offer.currency,
            expires_at=offer.expires_at,
            terms=offer.terms,
            status=offer.status,
            created_at=offer.created_at,
            updated_at=offer.updated_at,
        )

    def list_offers_for_authenticated_candidate(
        self,
        candidate: Candidate,
        *,
        active_only: bool = False,
    ) -> list[CandidateOfferResponse]:
        offers = self.offer_repository.list_owned_by_candidate(
            candidate.id,
            active_only=active_only,
        )
        return [self._to_candidate_offer_response(offer) for offer in offers]

    def get_offer_for_authenticated_candidate(
        self,
        candidate: Candidate,
        offer_id: UUID,
    ) -> CandidateOfferResponse:
        offer = self.offer_repository.get_by_id(offer_id)
        if offer is None or offer.application_id is None:
            raise LookupError("Offer not found")
        # Reuse the same ownership path as accept/decline — no parallel auth helper.
        self._authorize_candidate_for_offer(candidate, offer)
        return self._to_candidate_offer_response(offer)

    def list_offers_for_job(
        self,
        user: User,
        job_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = True,
    ) -> JobOfferListResponse:
        membership = self._require_staff_role(user, OFFER_READ_ROLES)
        company_id = membership.company_id
        job = self.application_service.job_repository.get_by_id_for_company(job_id, company_id)
        if job is None:
            raise LookupError("Job not found")

        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(int(page_size), 100))
        total = self.offer_repository.count_by_job_id_for_company(
            company_id,
            job_id,
            active_only=active_only,
        )
        total_pages = (total + normalized_page_size - 1) // normalized_page_size if total else 0
        offset = (normalized_page - 1) * normalized_page_size
        offers = self.offer_repository.list_by_job_id_for_company_paginated(
            company_id,
            job_id,
            offset=offset,
            limit=normalized_page_size,
            active_only=active_only,
        )
        return JobOfferListResponse(
            job_id=job_id,
            items=[self._to_job_offer_item(offer) for offer in offers],
            total=total,
            generated_at=datetime.now(timezone.utc),
            pagination=OfferPagination(
                page=normalized_page,
                page_size=normalized_page_size,
                total=total,
                pages=total_pages,
            ),
        )

    def update_offer(self, user: User, offer_id: UUID, payload: OfferUpdate) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_CONTENT_EDIT_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        self._require_active_offer(offer)

        current = normalize_offer_status(offer.status)
        if current not in {OfferStatus.DRAFT, OfferStatus.PENDING_APPROVAL}:
            raise ValueError("Only draft or pending_approval offers can be edited")

        updates: dict[str, Any] = payload.model_dump(exclude_unset=True)
        if not updates:
            return self._to_response(offer)

        if "compensation_min" in updates or "compensation_max" in updates:
            compensation_min = updates.get("compensation_min", offer.compensation_min)
            compensation_max = updates.get("compensation_max", offer.compensation_max)
            if compensation_min is not None and compensation_min < 0:
                raise ValueError("compensation_min cannot be negative")
            if compensation_max is not None and compensation_max < 0:
                raise ValueError("compensation_max cannot be negative")
            if (
                compensation_min is not None
                and compensation_max is not None
                and compensation_min > compensation_max
            ):
                raise ValueError("compensation_min cannot be greater than compensation_max")

        if "expires_at" in updates and updates["expires_at"] is not None:
            if updates["expires_at"] < datetime.now(timezone.utc):
                raise ValueError("expires_at cannot be in the past")

        updates["updated_at"] = datetime.now(timezone.utc)
        previous = self._offer_state_snapshot(offer)
        updated = self.offer_repository.update(offer, updates)
        self._audit_offer_event(
            user=user,
            action="offer_updated",
            offer=updated,
            company_id=membership.company_id,
            previous_state=previous,
            metadata={
                # Field names only — avoid logging offer terms/compensation payloads.
                "updated_fields": sorted(k for k in updates if k != "updated_at"),
            },
        )
        return self._to_response(updated)

    def submit_for_approval(self, user: User, offer_id: UUID) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_SUBMIT_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        application = self._get_application_for_company(offer.application_id, membership.company_id)
        self._assert_application_not_terminal(application)
        self._assert_hiring_decision_gate(company_id=membership.company_id, application_id=application.id)
        previous = self._offer_state_snapshot(offer)

        def _submit() -> Offer:
            updated = self._transition_active_offer(offer, OfferStatus.PENDING_APPROVAL, commit=False)
            self._sync_application_status(
                company_id=membership.company_id,
                application_id=application.id,
                target_status=ApplicationStatus.OFFERED,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_submit)
        self._db().refresh(updated)
        self._audit_offer_event(
            user=user,
            action="offer_submitted",
            offer=updated,
            company_id=membership.company_id,
            application=application,
            previous_state=previous,
        )
        if self.notification_events is not None:
            self.notification_events.offer_submitted(offer=updated, application=application)
        invalidate_company_reporting_cache(membership.company_id)
        return self._to_response(updated)

    def approve_offer(self, user: User, offer_id: UUID) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_APPROVE_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        application = self._get_application_for_company(offer.application_id, membership.company_id)
        self._assert_application_not_terminal(application)
        previous = self._offer_state_snapshot(offer)

        def _approve() -> Offer:
            updated = self._transition_active_offer(
                offer,
                OfferStatus.APPROVED,
                extra_updates={"approved_by_id": user.id},
                commit=False,
            )
            self._sync_application_status(
                company_id=membership.company_id,
                application_id=application.id,
                target_status=ApplicationStatus.OFFERED,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_approve)
        self._db().refresh(updated)
        self._audit_offer_event(
            user=user,
            action="offer_approved",
            offer=updated,
            company_id=membership.company_id,
            application=application,
            previous_state=previous,
            metadata={"approved_by_id": str(user.id)},
        )
        if self.notification_events is not None:
            self.notification_events.offer_approved(offer=updated, application=application)
        invalidate_company_reporting_cache(membership.company_id)
        return self._to_response(updated)

    def reject_offer(self, user: User, offer_id: UUID, reason: str | None = None) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_APPROVE_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        application = self._get_application_for_company(offer.application_id, membership.company_id)
        previous = self._offer_state_snapshot(offer)

        def _reject() -> Offer:
            updated = self._transition_failed_offer(offer, OfferStatus.REJECTED, commit=False)
            self._release_application_from_offer_stage(
                company_id=membership.company_id,
                application=application,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_reject)
        self._db().refresh(updated)
        self._audit_offer_event(
            user=user,
            action="offer_rejected",
            offer=updated,
            company_id=membership.company_id,
            application=application,
            previous_state=previous,
            metadata={"reason": reason},
        )
        if self.notification_events is not None:
            self.notification_events.offer_rejected(offer=updated, application=application)
        invalidate_company_reporting_cache(membership.company_id)
        return self._to_response(updated)

    def withdraw_offer(self, user: User, offer_id: UUID, reason: str | None = None) -> OfferResponse:
        membership = self._require_staff_role(user, OFFER_WITHDRAW_ROLES)
        offer = self._get_offer_for_company(offer_id, membership.company_id)
        application = self._get_application_for_company(offer.application_id, membership.company_id)
        previous = self._offer_state_snapshot(offer)

        def _withdraw() -> Offer:
            updated = self._transition_failed_offer(offer, OfferStatus.WITHDRAWN, commit=False)
            self._release_application_from_offer_stage(
                company_id=membership.company_id,
                application=application,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_withdraw)
        self._db().refresh(updated)
        self._audit_offer_event(
            user=user,
            action="offer_withdrawn",
            offer=updated,
            company_id=membership.company_id,
            application=application,
            previous_state=previous,
            metadata={"reason": reason},
        )
        if self.notification_events is not None:
            self.notification_events.offer_withdrawn(offer=updated, application=application)
        invalidate_company_reporting_cache(membership.company_id)
        return self._to_response(updated)

    def accept_offer(self, candidate: Candidate, offer_id: UUID) -> OfferResponse:
        # Candidate-facing: ownership via authenticated Candidate → Application → Offer.
        offer = self.offer_repository.get_by_id(offer_id)
        if offer is None or offer.application_id is None:
            raise LookupError("Offer not found")
        company_id = self._authorize_candidate_for_offer(candidate, offer)
        offer = self._get_offer_for_company(offer_id, company_id)
        application = self._get_application_for_company(offer.application_id, company_id)
        self._assert_application_not_terminal(application)
        previous = self._offer_state_snapshot(offer)

        def _accept() -> Offer:
            updated = self._transition_active_offer(offer, OfferStatus.ACCEPTED, commit=False)
            self._sync_application_status(
                company_id=company_id,
                application_id=application.id,
                target_status=ApplicationStatus.HIRED,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_accept)
        self._db().refresh(updated)
        self._audit_offer_event(
            candidate=candidate,
            action="offer_accepted",
            offer=updated,
            company_id=company_id,
            application=application,
            previous_state=previous,
        )
        if self.notification_events is not None:
            self.notification_events.offer_accepted(offer=updated, application=application)
        invalidate_company_reporting_cache(company_id)
        return self._to_response(updated)

    def decline_offer(self, candidate: Candidate, offer_id: UUID, reason: str | None = None) -> OfferResponse:
        offer = self.offer_repository.get_by_id(offer_id)
        if offer is None or offer.application_id is None:
            raise LookupError("Offer not found")
        company_id = self._authorize_candidate_for_offer(candidate, offer)
        offer = self._get_offer_for_company(offer_id, company_id)
        application = self._get_application_for_company(offer.application_id, company_id)
        previous = self._offer_state_snapshot(offer)

        def _decline() -> Offer:
            updated = self._transition_failed_offer(offer, OfferStatus.DECLINED, commit=False)
            # Candidate declined the current offer only — allow a revised offer path.
            self._release_application_from_offer_stage(
                company_id=company_id,
                application=application,
                commit=False,
            )
            return updated

        updated = self._run_transaction(_decline)
        self._db().refresh(updated)
        self._audit_offer_event(
            candidate=candidate,
            action="offer_declined",
            offer=updated,
            company_id=company_id,
            application=application,
            previous_state=previous,
            metadata={"reason": reason},
        )
        if self.notification_events is not None:
            self.notification_events.offer_declined(offer=updated, application=application)
        return self._to_response(updated)
