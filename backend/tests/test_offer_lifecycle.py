"""Critical Offer Management domain invariant tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.application_status import ApplicationStatus
from app.core.offer_status import OfferStatus
from app.models.offer import Offer
from app.schemas.offer import OfferUpdate
from app.services.recruiter_workspace import RecruiterWorkspaceService
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


def test_cross_company_offer_access_is_rejected(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    with pytest.raises(LookupError, match="Offer not found"):
        world.offer_service.get_offer(world.other_recruiter, created.id)


def test_unauthorized_role_cannot_create_or_approve(world: OfferWorld) -> None:
    with pytest.raises(PermissionError):
        world.offer_service.create_offer_for_application(
            world.viewer,
            world.application.id,
            world.offer_payload(),
        )

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    with pytest.raises(PermissionError):
        world.offer_service.approve_offer(world.recruiter, submitted.id)
    with pytest.raises(PermissionError):
        world.offer_service.approve_offer(world.viewer, submitted.id)


def test_offer_creation_requires_application_and_hiring_gate(world: OfferWorld) -> None:
    missing_application_id = uuid4()
    with pytest.raises(LookupError, match="Application not found"):
        world.offer_service.create_offer_for_application(
            world.recruiter,
            missing_application_id,
            world.offer_payload(application_id=missing_application_id),
        )

    world.decision.recommendation = "Consider"
    world.decision.recruiter_override = None
    world.db.add(world.decision)
    world.db.commit()

    with pytest.raises(ValueError, match="not eligible"):
        world.offer_service.create_offer_for_application(
            world.recruiter,
            world.application.id,
            world.offer_payload(),
        )


def test_hiring_decision_override_gate_enables_offer(world: OfferWorld) -> None:
    world.decision.recommendation = "Reject"
    world.decision.recruiter_override = None
    world.db.add(world.decision)
    world.db.commit()

    with pytest.raises(ValueError, match="not eligible"):
        world.offer_service.create_offer_for_application(
            world.recruiter,
            world.application.id,
            world.offer_payload(),
        )

    world.decision.recruiter_override = {
        "recommendation": "Hire",
        "reason": "Strong interview calibration",
        "comment": None,
        "overridden_by_user_id": str(world.recruiter.id),
        "overridden_at": datetime.now(timezone.utc).isoformat(),
        "original_recommendation": "Reject",
    }
    world.db.add(world.decision)
    world.db.commit()

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    assert created.status == OfferStatus.DRAFT
    assert created.application_id == world.application.id


def test_invalid_offer_transitions_rejected(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    with pytest.raises(ValueError, match="Invalid offer status transition"):
        world.offer_service.approve_offer(world.hiring_manager, created.id)


def test_revision_supersedes_previous_and_keeps_history_immutable(world: OfferWorld) -> None:
    first = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, first.id)
    world.offer_service.withdraw_offer(world.recruiter, submitted.id, reason="revise package")

    application = world.refresh_application()
    assert application.status == ApplicationStatus.INTERVIEW.value
    assert world.count_active_offers() == 0

    second = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    assert second.revision == 2
    assert second.supersedes_offer_id == first.id
    assert second.is_active is True
    assert world.count_active_offers() == 1

    history = world.offer_service.get_application_offer_history(world.recruiter, world.application.id)
    assert history.total_revisions == 2
    assert history.current_offer is not None
    assert history.current_offer.id == second.id
    assert {item.id for item in history.revisions} == {first.id, second.id}

    # Historical / superseded offers cannot be modified or accepted.
    with pytest.raises(ValueError):
        world.offer_service.update_offer(
            world.recruiter,
            first.id,
            OfferUpdate(offer_title="tamper"),
        )
    with pytest.raises(ValueError):
        world.offer_service.accept_offer(world.candidate, first.id)


def test_blocking_active_offer_prevents_parallel_revision(world: OfferWorld) -> None:
    first = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    world.offer_service.submit_for_approval(world.recruiter, first.id)
    with pytest.raises(ValueError, match="active offer already exists"):
        world.offer_service.create_offer_for_application(
            world.recruiter,
            world.application.id,
            world.offer_payload(),
        )


def test_accept_syncs_application_to_hired(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    assert world.refresh_application().status == ApplicationStatus.OFFERED.value

    accepted = world.offer_service.accept_offer(world.candidate, approved.id)
    assert accepted.status == OfferStatus.ACCEPTED
    assert world.refresh_application().status == ApplicationStatus.HIRED.value


def test_reject_and_decline_preserve_revision_path(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    world.offer_service.reject_offer(world.hiring_manager, submitted.id, reason="comp")
    assert world.refresh_application().status == ApplicationStatus.INTERVIEW.value

    revised = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted2 = world.offer_service.submit_for_approval(world.recruiter, revised.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted2.id)
    world.offer_service.decline_offer(world.candidate, approved.id, reason="counter")
    assert world.refresh_application().status == ApplicationStatus.INTERVIEW.value

    third = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    assert third.revision == 3
    assert third.is_active is True


def test_submit_transaction_rolls_back_on_application_sync_failure(
    world: OfferWorld,
    monkeypatch,
) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )

    def _boom(**_kwargs):
        raise ValueError("forced sync failure")

    monkeypatch.setattr(
        world.offer_service.application_service,
        "apply_status_transition",
        _boom,
    )

    with pytest.raises(ValueError, match="forced sync failure"):
        world.offer_service.submit_for_approval(world.recruiter, created.id)

    offer = world.db.get(Offer, created.id)
    assert offer is not None
    assert offer.status == OfferStatus.DRAFT.value
    assert world.refresh_application().status == ApplicationStatus.INTERVIEW.value


def test_repository_default_commit_remains_compatible(world: OfferWorld) -> None:
    repo = world.offer_service.offer_repository
    orphan = Offer(
        application_id=world.application.id,
        candidate_id=world.candidate.id,
        job_id=world.job.id,
        created_by_id=world.recruiter.id,
        revision=99,
        is_active=False,
        offer_title="compat",
        compensation_min=1,
        compensation_max=2,
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        status=OfferStatus.DRAFT.value,
    )
    created = repo.create(orphan)  # default commit=True
    assert created.id is not None
    assert world.db.get(Offer, created.id) is not None


def test_recruiter_workspace_pending_offers_use_offer_state(world: OfferWorld) -> None:
    world.candidate.status = "offer"
    world.db.add(world.candidate)
    world.db.commit()

    workspace = RecruiterWorkspaceService(db=world.db)
    pending_before = workspace.get_pending_offers_for_user(world.recruiter)
    assert pending_before == []

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    world.offer_service.submit_for_approval(world.recruiter, created.id)

    pending = workspace.get_pending_offers_for_user(world.recruiter)
    assert len(pending) == 1
    assert pending[0].metadata["offer_id"] == str(created.id)
    assert pending[0].metadata["offer_status"] == OfferStatus.PENDING_APPROVAL.value
    assert pending[0].status == OfferStatus.PENDING_APPROVAL.value


def test_non_candidate_accept_does_not_leak_offer_existence(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)

    with pytest.raises(LookupError, match="Offer not found"):
        world.offer_service.accept_offer(world.other_candidate, approved.id)

    with pytest.raises(LookupError, match="Offer not found"):
        world.offer_service.decline_offer(world.other_candidate, approved.id, reason="probe")


def test_repeated_lifecycle_transition_rejected(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    world.offer_service.withdraw_offer(world.recruiter, created.id)
    with pytest.raises(ValueError):
        world.offer_service.withdraw_offer(world.recruiter, created.id)


def test_active_offer_unique_constraint_maps_to_domain_error(world: OfferWorld, monkeypatch) -> None:
    world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    # Bypass the service-level active check to force the DB partial-unique path.
    monkeypatch.setattr(
        world.offer_service.offer_repository,
        "get_active_by_application_id_for_company",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ValueError, match="concurrent update"):
        world.offer_service.create_offer_for_application(
            world.recruiter,
            world.application.id,
            world.offer_payload(),
        )


def test_offer_update_audit_excludes_sensitive_field_values(world: OfferWorld, monkeypatch) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    captured: list[dict] = []

    def _capture_log(**kwargs):
        captured.append(kwargs)
        return "audit-id"

    monkeypatch.setattr("app.services.offer_service.audit_service.log", _capture_log)
    world.offer_service.update_offer(
        world.recruiter,
        created.id,
        OfferUpdate(terms="SECRET compensation clause", offer_title="Updated title"),
    )
    assert captured
    metadata = captured[-1]["metadata"]
    assert metadata["updated_fields"] == ["offer_title", "terms"]
    assert "SECRET" not in str(metadata)
    assert "updates" not in metadata
