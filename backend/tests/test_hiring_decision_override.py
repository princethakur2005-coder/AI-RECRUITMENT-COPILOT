"""Regression: recruiter override can bootstrap hiring decisions for offer gating."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_USER
from app.core.jwt import create_access_token
from app.db.database import get_db
from app.main import app
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


@pytest.fixture
def api_client(world: OfferWorld) -> TestClient:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
    app.dependency_overrides.clear()


def test_recruiter_override_bootstraps_decision_and_unlocks_offer(api_client: TestClient, world: OfferWorld) -> None:
    from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository

    application_id = world.application.id
    decision_repo = ApplicationHiringDecisionRepository(world.db)

    # Remove the seeded AI decision so override must bootstrap.
    if world.decision is not None:
        decision_repo.delete(world.decision)
        world.decision = None
        world.db.commit()

    missing = api_client.get(f"/applications/{application_id}/hiring-decision")
    assert missing.status_code == 404

    blocked = api_client.post(
        f"/applications/{application_id}/offers",
        json={
            "offer_title": "Backend Offer",
            "compensation_min": 120000,
            "compensation_max": 140000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "terms": "Standard",
        },
    )
    assert blocked.status_code == 400
    assert "hiring decision" in blocked.json()["detail"].lower()

    override = api_client.put(
        f"/applications/{application_id}/hiring-decision/override",
        json={"recommendation": "Hire", "reason": "Selected after interview loop"},
    )
    assert override.status_code == 200, override.text
    body = override.json()
    assert body["recommendation"] == "Hire"
    assert body["recruiter_override"]["recommendation"] == "Hire"
    assert body["decision_detail"]["source"]["type"] == "recruiter_override_bootstrap"

    loaded = api_client.get(f"/applications/{application_id}/hiring-decision")
    assert loaded.status_code == 200
    assert loaded.json()["id"] == body["id"]

    created = api_client.post(
        f"/applications/{application_id}/offers",
        json={
            "offer_title": "Backend Offer",
            "compensation_min": 120000,
            "compensation_max": 140000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "terms": "Standard",
        },
    )
    assert created.status_code == 201, created.text


def test_candidate_cannot_override_hiring_decision(world: OfferWorld) -> None:
    from app.core.auth_principals import PRINCIPAL_CANDIDATE

    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    token = create_access_token(world.candidate.id, principal=PRINCIPAL_CANDIDATE)
    client.headers.update({"Authorization": f"Bearer {token}"})
    try:
        response = client.put(
            f"/applications/{world.application.id}/hiring-decision/override",
            json={"recommendation": "Hire", "reason": "Should not work"},
        )
        assert response.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()
