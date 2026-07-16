from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.models.offer import Offer
from app.repositories.offer import OfferRepository
from app.schemas.offer import (
    CompensationSummary,
    OfferCreate,
    OfferHiringIntelligence,
    OfferResponse,
    OfferValidationIssue,
    OfferValidationResult,
)
from app.services.base import BaseService


class OfferService(BaseService[Offer]):
    """Service layer for offer-related operations."""

    _ALLOWED_STATUSES = {
        "draft",
        "pending_approval",
        "approved",
        "rejected",
        "accepted",
        "declined",
        "expired",
        # Legacy compatibility aliases.
        "pending",
        "withdrawn",
    }
    _STATUS_ALIASES = {
        "pending": "pending_approval",
        "withdrawn": "declined",
    }
    _ALLOWED_TRANSITIONS = {
        "draft": {"pending_approval"},
        "pending_approval": {"approved", "rejected"},
        "approved": {"accepted", "declined", "expired"},
        "accepted": set(),
        "rejected": set(),
        "declined": set(),
        "expired": set(),
    }

    def __init__(self, repository: OfferRepository) -> None:
        super().__init__(repository)

    def create_offer(self, offer_in: OfferCreate, created_by_id: UUID | None = None) -> OfferResponse:
        self._validate_offer_create(offer_in)
        offer = Offer(
            candidate_id=offer_in.candidate_id,
            job_id=offer_in.job_id,
            created_by_id=created_by_id,
            offer_title=offer_in.offer_title,
            compensation_min=offer_in.compensation_min,
            compensation_max=offer_in.compensation_max,
            currency=offer_in.currency,
            expires_at=offer_in.expires_at,
            terms=offer_in.terms,
            # Keep existing behavior compatible with prior "pending" records.
            status="pending",
        )
        created = super().create(offer)
        return self._to_offer_response(created)

    def get_offer(self, offer_id: UUID) -> OfferResponse | None:
        offer = self.repository.get_by_id(offer_id)
        if offer is None:
            return None
        return self._to_offer_response(offer)

    def update_offer_status(self, offer_id: UUID, status: str, approved_by_id: UUID | None = None) -> OfferResponse | None:
        offer = self.repository.get_by_id(offer_id)
        if offer is None:
            return None

        self._validate_status_transition(offer.status, status)
        update_payload = {"status": status}
        normalized_next = self._normalize_status(status)
        if normalized_next == "approved":
            if approved_by_id is None:
                raise ValueError("approved_by_id is required when approving an offer")
            update_payload["approved_by_id"] = approved_by_id
        updated = super().update(offer, update_payload)
        return self._to_offer_response(updated)

    def submit_for_approval(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="pending_approval")

    def approve_offer(self, offer_id: UUID, approved_by_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="approved", approved_by_id=approved_by_id)

    def reject_offer(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="rejected")

    def withdraw_offer(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="withdrawn")

    def accept_offer(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="accepted")

    def decline_offer(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="declined")

    def expire_offer(self, offer_id: UUID) -> OfferResponse | None:
        return self.update_offer_status(offer_id=offer_id, status="expired")

    def _validate_offer_create(self, offer_in: OfferCreate) -> None:
        required_field_values = {
            "offer_title": offer_in.offer_title,
            "compensation_min": offer_in.compensation_min,
            "compensation_max": offer_in.compensation_max,
            "currency": offer_in.currency,
            "expires_at": offer_in.expires_at,
        }
        missing_required = [field for field, value in required_field_values.items() if value in (None, "")]
        if missing_required:
            raise ValueError(f"Missing required offer fields: {', '.join(missing_required)}")

        if offer_in.compensation_min is not None and offer_in.compensation_min < 0:
            raise ValueError("compensation_min cannot be negative")
        if offer_in.compensation_max is not None and offer_in.compensation_max < 0:
            raise ValueError("compensation_max cannot be negative")
        if (
            offer_in.compensation_min is not None
            and offer_in.compensation_max is not None
            and offer_in.compensation_min > offer_in.compensation_max
        ):
            raise ValueError("compensation_min cannot be greater than compensation_max")
        if offer_in.expires_at is not None and offer_in.expires_at < datetime.now(timezone.utc):
            raise ValueError("expires_at cannot be in the past")

    def _validate_status_transition(self, current_status: str, next_status: str) -> None:
        normalized_current = self._normalize_status(current_status)
        normalized_next = self._normalize_status(next_status)

        if normalized_next not in self._ALLOWED_TRANSITIONS:
            raise ValueError("Invalid offer status")
        if normalized_current == normalized_next:
            return
        allowed_next = self._ALLOWED_TRANSITIONS.get(normalized_current, set())
        if normalized_next not in allowed_next:
            raise ValueError(f"Invalid offer status transition: {current_status} -> {next_status}")

    def _normalize_status(self, status: str) -> str:
        if status not in self._ALLOWED_STATUSES:
            raise ValueError("Invalid offer status")
        return self._STATUS_ALIASES.get(status, status)

    def _approval_status_for_offer(self, offer: Offer) -> str:
        normalized_status = self._normalize_status(offer.status)
        if normalized_status == "approved":
            return "approved"
        if normalized_status in {"rejected", "declined", "expired", "accepted"}:
            return "closed"
        if normalized_status == "pending_approval":
            return "pending_approval"
        if normalized_status == "draft":
            return "draft"
        return "pending"

    def _collect_validation_issues(self, offer: Offer) -> list[OfferValidationIssue]:
        issues: list[OfferValidationIssue] = []

        required_field_values = {
            "offer_title": offer.offer_title,
            "compensation_min": offer.compensation_min,
            "compensation_max": offer.compensation_max,
            "currency": offer.currency,
            "expires_at": offer.expires_at,
        }
        for field, value in required_field_values.items():
            if value in (None, ""):
                issues.append(
                    OfferValidationIssue(
                        code="required_field_missing",
                        field=field,
                        message=f"{field} is required",
                    )
                )

        if offer.compensation_min is not None and offer.compensation_min < 0:
            issues.append(
                OfferValidationIssue(
                    code="invalid_compensation_min",
                    field="compensation_min",
                    message="compensation_min cannot be negative",
                )
            )
        if offer.compensation_max is not None and offer.compensation_max < 0:
            issues.append(
                OfferValidationIssue(
                    code="invalid_compensation_max",
                    field="compensation_max",
                    message="compensation_max cannot be negative",
                )
            )
        if (
            offer.compensation_min is not None
            and offer.compensation_max is not None
            and offer.compensation_min > offer.compensation_max
        ):
            issues.append(
                OfferValidationIssue(
                    code="compensation_range_invalid",
                    field="compensation_min",
                    message="compensation_min cannot be greater than compensation_max",
                )
            )

        now = datetime.now(timezone.utc)
        if offer.expires_at is not None and offer.expires_at < now and self._normalize_status(offer.status) != "expired":
            issues.append(
                OfferValidationIssue(
                    code="expiry_inconsistent",
                    field="expires_at",
                    message="Offer expiry date is in the past but status is not expired",
                )
            )

        normalized_status = self._normalize_status(offer.status)
        approval_status = self._approval_status_for_offer(offer)
        if normalized_status == "approved" and offer.approved_by_id is None:
            issues.append(
                OfferValidationIssue(
                    code="approval_inconsistent",
                    field="approved_by_id",
                    message="approved_by_id is required when status is approved",
                )
            )
        if normalized_status in {"draft", "pending_approval"} and approval_status not in {"draft", "pending_approval", "pending"}:
            issues.append(
                OfferValidationIssue(
                    code="approval_status_inconsistent",
                    field="status",
                    message="approval status is inconsistent with offer state",
                )
            )

        if normalized_status not in self._ALLOWED_TRANSITIONS:
            issues.append(
                OfferValidationIssue(
                    code="state_invalid",
                    field="status",
                    message="Offer status is not part of the supported state machine",
                )
            )

        return issues

    def _to_offer_response(self, offer: Offer) -> OfferResponse:
        validation_issues = self._collect_validation_issues(offer)
        return OfferResponse(
            id=offer.id,
            candidate_id=offer.candidate_id,
            job_id=offer.job_id,
            created_by_id=offer.created_by_id,
            approved_by_id=offer.approved_by_id,
            offer_title=offer.offer_title,
            compensation_min=offer.compensation_min,
            compensation_max=offer.compensation_max,
            currency=offer.currency,
            expires_at=offer.expires_at,
            terms=offer.terms,
            status=offer.status,
            hiring_intelligence=OfferHiringIntelligence(
                offer_status=offer.status,
                proposed_role=offer.offer_title,
                compensation_summary=CompensationSummary(
                    minimum=offer.compensation_min,
                    maximum=offer.compensation_max,
                    currency=offer.currency,
                ),
                start_date=None,
                expiry_date=offer.expires_at,
                approval_status=self._approval_status_for_offer(offer),
            ),
            validation=OfferValidationResult(
                is_valid=not validation_issues,
                issues=validation_issues,
            ),
            created_at=offer.created_at,
            updated_at=offer.updated_at,
        )
