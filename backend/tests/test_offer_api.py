"""API contract coverage for production Offer endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import create_access_token
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.candidate import Candidate
from app.models.user import User
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


@pytest.fixture
def api_client(world: OfferWorld) -> Callable[[User], TestClient]:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db

    def _as(user: User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _as
    app.dependency_overrides.clear()


@pytest.fixture
def candidate_api_client(world: OfferWorld) -> Callable[[Candidate], TestClient]:
    """Real candidate JWT auth (no dependency override of get_current_candidate)."""

    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    # Ensure recruiter override from other fixtures cannot leak into candidate auth.
    app.dependency_overrides.pop(get_current_user, None)

    def _as(candidate: Candidate) -> TestClient:
        token = create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)
        client = TestClient(app)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    yield _as
    app.dependency_overrides.clear()


def _approve_offer(api_client, world: OfferWorld) -> str:
    created = api_client(world.recruiter).post(
        f"/applications/{world.application.id}/offers",
        json={
            "offer_title": "Candidate Action Offer",
            "compensation_min": 100000,
            "compensation_max": 120000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            "terms": "Standard",
        },
    )
    assert created.status_code == 201, created.text
    offer_id = created.json()["id"]
    submitted = api_client(world.recruiter).post(f"/offers/{offer_id}/submit")
    assert submitted.status_code == 200
    approved = api_client(world.hiring_manager).post(f"/offers/{offer_id}/approve")
    assert approved.status_code == 200
    return offer_id


def test_offer_endpoints_require_authentication(world: OfferWorld) -> None:
    app.dependency_overrides.clear()

    def _override_db():
        yield world.db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    response = client.get(f"/applications/{world.application.id}/offers/current")
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_application_offer_reads_and_history_contracts(api_client, world: OfferWorld) -> None:
    client = api_client(world.recruiter)
    create_body = {
        "offer_title": "Backend Engineer Offer",
        "compensation_min": 100000,
        "compensation_max": 120000,
        "currency": "USD",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        "terms": "Standard",
    }
    created = client.post(f"/applications/{world.application.id}/offers", json=create_body)
    assert created.status_code == 201, created.text
    offer = created.json()
    assert offer["application_id"] == str(world.application.id)
    assert offer["status"] == "draft"
    assert offer["is_active"] is True
    assert offer["revision"] == 1

    current = client.get(f"/applications/{world.application.id}/offers/current")
    assert current.status_code == 200
    assert current.json()["id"] == offer["id"]

    active = client.get(f"/applications/{world.application.id}/offers/active")
    assert active.status_code == 200
    assert active.json()["id"] == offer["id"]

    history = client.get(f"/applications/{world.application.id}/offers/history")
    assert history.status_code == 200
    payload = history.json()
    assert payload["application_id"] == str(world.application.id)
    assert payload["total_revisions"] == 1
    assert payload["current_offer"]["id"] == offer["id"]
    assert isinstance(payload["revisions"], list)


def test_cross_tenant_api_isolation_and_rbac(api_client, world: OfferWorld) -> None:
    created = api_client(world.recruiter).post(
        f"/applications/{world.application.id}/offers",
        json={
            "offer_title": "Offer",
            "compensation_min": 90000,
            "compensation_max": 110000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        },
    )
    assert created.status_code == 201
    offer_id = created.json()["id"]

    assert api_client(world.other_recruiter).get(f"/offers/{offer_id}").status_code == 404

    forbidden = api_client(world.viewer).post(
        f"/applications/{world.application.id}/offers",
        json={
            "offer_title": "No",
            "compensation_min": 1,
            "compensation_max": 2,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
    )
    assert forbidden.status_code == 403


def test_lifecycle_mutations_and_error_mapping(api_client, world: OfferWorld) -> None:
    created = api_client(world.recruiter).post(
        f"/applications/{world.application.id}/offers",
        json={
            "offer_title": "Lifecycle",
            "compensation_min": 100000,
            "compensation_max": 125000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    offer_id = created.json()["id"]

    bad_approve = api_client(world.hiring_manager).post(f"/offers/{offer_id}/approve")
    assert bad_approve.status_code == 400

    submitted = api_client(world.recruiter).post(f"/offers/{offer_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_approval"

    approved = api_client(world.hiring_manager).post(f"/offers/{offer_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    jobs = api_client(world.recruiter).get(f"/jobs/{world.job.id}/offers")
    assert jobs.status_code == 200
    body = jobs.json()
    assert body["job_id"] == str(world.job.id)
    assert body["total"] >= 1
    assert "pagination" in body
    assert isinstance(body["items"], list)


def test_compatibility_offer_create_delegates_to_offer_service(api_client, world: OfferWorld) -> None:
    response = api_client(world.recruiter).post(
        "/offers",
        json={
            "application_id": str(world.application.id),
            "offer_title": "Compat",
            "compensation_min": 95000,
            "compensation_max": 115000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=8)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["application_id"] == str(world.application.id)
    assert data["is_active"] is True

    listed = api_client(world.recruiter).get(f"/offers/candidate/{world.candidate.id}")
    assert listed.status_code == 200
    assert any(item["id"] == data["id"] for item in listed.json())


def test_authenticated_candidate_can_accept_own_offer(
    api_client,
    candidate_api_client,
    world: OfferWorld,
) -> None:
    offer_id = _approve_offer(api_client, world)
    accepted = candidate_api_client(world.candidate).post(f"/offers/{offer_id}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"


def test_authenticated_candidate_can_decline_own_offer(
    api_client,
    candidate_api_client,
    world: OfferWorld,
) -> None:
    offer_id = _approve_offer(api_client, world)
    declined = candidate_api_client(world.candidate).post(
        f"/offers/{offer_id}/decline",
        params={"reason": "timing"},
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"


def test_candidate_cannot_accept_or_decline_another_candidates_offer(
    api_client,
    candidate_api_client,
    world: OfferWorld,
) -> None:
    offer_id = _approve_offer(api_client, world)

    accept = candidate_api_client(world.other_candidate).post(f"/offers/{offer_id}/accept")
    assert accept.status_code == 404
    assert accept.json()["message"] == "Offer not found"

    decline = candidate_api_client(world.other_candidate).post(f"/offers/{offer_id}/decline")
    assert decline.status_code == 404
    assert decline.json()["message"] == "Offer not found"


def test_candidate_accept_requires_candidate_token(api_client, world: OfferWorld) -> None:
    offer_id = _approve_offer(api_client, world)

    app.dependency_overrides.pop(get_current_user, None)

    def _override_db():
        yield world.db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    unauthenticated = client.post(f"/offers/{offer_id}/accept")
    assert unauthenticated.status_code == 401

    # Same-email recruiter/user JWT must not impersonate candidate identity.
    user_token = create_access_token(world.candidate_user.id, principal=PRINCIPAL_USER)
    as_user = client.post(
        f"/offers/{offer_id}/accept",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert as_user.status_code == 401

    recruiter_token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
    as_recruiter = client.post(
        f"/offers/{offer_id}/accept",
        headers={"Authorization": f"Bearer {recruiter_token}"},
    )
    assert as_recruiter.status_code == 401

    app.dependency_overrides.clear()
