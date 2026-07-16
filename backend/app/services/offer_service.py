from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from app.models.offer import Offer
from app.models.user import User
from app.repositories.offer import OfferRepository
from app.services.audit_service import audit_service
from app.services.base import BaseService
from app.services.hiring_workflow import CandidateLifecycleManager


class OfferService(BaseService[Offer]):
    """Service layer for offer lifecycle management with workflow integration."""

    VALID_STATUSES = {"pending", "approved", "accepted", "rejected", "withdrawn"}

    def __init__(self, repository: OfferRepository, workflow: CandidateLifecycleManager | None = None) -> None:
        super().__init__(repository)
        self.repository = repository
        self.workflow = workflow or CandidateLifecycleManager()

    def create_offer(self, offer: Offer, author: User | None = None) -> Offer:
        offer.status = "pending"
        created = super().create(offer)
        audit_service.log(
            actor_id=str(author.id) if author else "system",
            actor_type="user" if author else "system",
            action="offer_created",
            resource_type="candidate",
            resource_id=str(created.candidate_id),
            metadata={
                "offer_id": str(created.id),
                "job_id": str(created.job_id) if created.job_id else None,
                "status": created.status,
            },
        )
        return created

    def approve_offer(self, offer: Offer, approver: User) -> Offer:
        if offer.status != "pending":
            raise ValueError("Only pending offers can be approved.")

        offer.status = "approved"
        offer.approved_by_id = approver.id
        updated = self.repository.update(offer, {"status": "approved", "approved_by_id": approver.id})
        audit_service.log(
            actor_id=str(approver.id),
            actor_type="user",
            action="offer_approved",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={"offer_id": str(updated.id), "approved_by_id": str(approver.id)},
        )
        self.workflow.move_to(str(updated.candidate_id), "Offer", str(approver.id), reason="offer_approved")
        return updated

    def accept_offer(self, offer: Offer, actor: User) -> Offer:
        if offer.status not in {"approved", "pending"}:
            raise ValueError("Only approved or pending offers can be accepted.")

        updated = self.repository.update(offer, {"status": "accepted"})
        audit_service.log(
            actor_id=str(actor.id),
            actor_type="user",
            action="offer_accepted",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={"offer_id": str(updated.id), "status": updated.status},
        )
        self.workflow.move_to(str(updated.candidate_id), "Hired", str(actor.id), reason="offer_accepted")
        return updated

    def reject_offer(self, offer: Offer, actor: User, reason: str | None = None) -> Offer:
        if offer.status not in {"pending", "approved"}:
            raise ValueError("Only pending or approved offers can be rejected.")

        updated = self.repository.update(offer, {"status": "rejected"})
        audit_service.log(
            actor_id=str(actor.id),
            actor_type="user",
            action="offer_rejected",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={"offer_id": str(updated.id), "reason": reason},
        )
        self.workflow.move_to(str(updated.candidate_id), "Rejected", str(actor.id), reason="offer_rejected")
        return updated

    def withdraw_offer(self, offer: Offer, actor: User, reason: str | None = None) -> Offer:
        if offer.status not in {"pending", "approved"}:
            raise ValueError("Only pending or approved offers can be withdrawn.")

        updated = self.repository.update(offer, {"status": "withdrawn"})
        audit_service.log(
            actor_id=str(actor.id),
            actor_type="user",
            action="offer_withdrawn",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={"offer_id": str(updated.id), "reason": reason},
        )
        self.workflow.move_to(str(updated.candidate_id), "Rejected", str(actor.id), reason="offer_withdrawn")
        return updated

    def list_candidate_offers(self, candidate_id: str) -> list[Offer]:
        return self.repository.list_by_candidate(candidate_id)

    def get_offer(self, offer_id: str) -> Offer | None:
        return self.repository.get_by_id(offer_id)

    def list_offers_by_status(self, status: str) -> list[Offer]:
        return self.repository.list_by_status(status)

    def update_offer(self, offer: Offer, updates: Dict[str, Any]) -> Offer:
        if "status" in updates and updates["status"] not in self.VALID_STATUSES:
            raise ValueError(f"Invalid offer status: {updates['status']}")
        updated = self.repository.update(offer, updates)
        audit_service.log(
            actor_id=str(updated.created_by_id) if updated.created_by_id else "system",
            actor_type="user" if updated.created_by_id else "system",
            action="offer_updated",
            resource_type="candidate",
            resource_id=str(updated.candidate_id),
            metadata={"offer_id": str(updated.id), "updates": updates},
        )
        return updated
