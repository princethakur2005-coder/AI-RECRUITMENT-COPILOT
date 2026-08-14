"""Candidate Portal API foundation — applications, interviews, offers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType
from app.core.jwt import create_access_token
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.candidate import Candidate
from app.models.interview import Interview
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
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)

    def _as(candidate: Candidate) -> TestClient:
        token = create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)
        client = TestClient(app)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    yield _as
    app.dependency_overrides.clear()


def _create_interview(world: OfferWorld, *, for_other: bool = False) -> Interview:
    application = world.other_application if for_other else world.application
    member = world.other_member if for_other else world.recruiter_member
    company = world.other_company if for_other else world.company
    start = datetime.now(timezone.utc) + timedelta(days=2)
    interview = Interview(
        application_id=application.id,
        company_id=company.id,
        interviewer_member_id=member.id,
        interview_type=InterviewType.TECHNICAL.value,
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=1),
        timezone="UTC",
        meeting_link="https://meet.example.com/room",
        location="Remote",
        notes="INTERNAL recruiter notes — must not leak",
        status=InterviewStatus.SCHEDULED.value,
    )
    world.db.add(interview)
    world.db.commit()
    world.db.refresh(interview)
    return interview


def _approve_offer(api_client, world: OfferWorld) -> str:
    created = api_client(world.recruiter).post(
        f"/applications/{world.application.id}/offers",
        json={
            "offer_title": "Portal Offer",
            "compensation_min": 100000,
            "compensation_max": 120000,
            "currency": "USD",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            "terms": "Standard",
        },
    )
    assert created.status_code == 201, created.text
    offer_id = created.json()["id"]
    assert api_client(world.recruiter).post(f"/offers/{offer_id}/submit").status_code == 200
    assert api_client(world.hiring_manager).post(f"/offers/{offer_id}/approve").status_code == 200
    return offer_id


def test_candidate_can_list_own_applications(candidate_api_client, world: OfferWorld) -> None:
    response = candidate_api_client(world.candidate).get("/candidate/applications")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    item = payload[0]
    assert item["id"] == str(world.application.id)
    assert item["job_title"] == world.job.title
    assert item["company_name"] == world.company.name
    assert "resume_path" not in item
    assert "candidate_id" not in item


def test_candidate_cannot_access_another_application(candidate_api_client, world: OfferWorld) -> None:
    response = candidate_api_client(world.candidate).get(
        f"/candidate/applications/{world.other_application.id}"
    )
    assert response.status_code == 404
    assert response.json()["message"] == "Application not found"


def test_candidate_can_read_own_interviews(candidate_api_client, world: OfferWorld) -> None:
    own = _create_interview(world, for_other=False)
    _create_interview(world, for_other=True)

    listed = candidate_api_client(world.candidate).get("/candidate/interviews")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == str(own.id)
    assert rows[0]["meeting_link"] == "https://meet.example.com/room"
    assert "notes" not in rows[0]
    assert rows[0]["interviewer_name"] == world.recruiter.full_name

    detail = candidate_api_client(world.candidate).get(f"/candidate/interviews/{own.id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == str(own.id)


def test_candidate_cannot_access_another_interview(candidate_api_client, world: OfferWorld) -> None:
    other = _create_interview(world, for_other=True)
    response = candidate_api_client(world.candidate).get(f"/candidate/interviews/{other.id}")
    assert response.status_code == 404
    assert response.json()["message"] == "Interview not found"


def test_candidate_can_read_own_offers(api_client, candidate_api_client, world: OfferWorld) -> None:
    offer_id = _approve_offer(api_client, world)

    listed = candidate_api_client(world.candidate).get("/candidate/offers")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(item["id"] == offer_id for item in rows)
    sample = next(item for item in rows if item["id"] == offer_id)
    assert "created_by_id" not in sample
    assert "approved_by_id" not in sample
    assert "hiring_intelligence" not in sample

    detail = candidate_api_client(world.candidate).get(f"/candidate/offers/{offer_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == offer_id
    assert detail.json()["status"] == "approved"


def test_candidate_cannot_access_another_offer(api_client, candidate_api_client, world: OfferWorld) -> None:
    offer_id = _approve_offer(api_client, world)
    response = candidate_api_client(world.other_candidate).get(f"/candidate/offers/{offer_id}")
    assert response.status_code == 404
    assert response.json()["message"] == "Offer not found"


def test_candidate_portal_requires_candidate_jwt(api_client, world: OfferWorld) -> None:
    app.dependency_overrides.pop(get_current_user, None)

    def _override_db():
        yield world.db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    assert client.get("/candidate/applications").status_code == 401

    user_token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
    as_recruiter = client.get(
        "/candidate/applications",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert as_recruiter.status_code == 401

    same_email_user = create_access_token(world.candidate_user.id, principal=PRINCIPAL_USER)
    as_same_email = client.get(
        "/candidate/offers",
        headers={"Authorization": f"Bearer {same_email_user}"},
    )
    assert as_same_email.status_code == 401

    app.dependency_overrides.clear()


def test_candidate_ownership_ignores_request_identity_hints(
    candidate_api_client,
    world: OfferWorld,
) -> None:
    # Query params / path identity hints must not expand access beyond JWT subject.
    response = candidate_api_client(world.candidate).get(
        "/candidate/applications",
        params={"candidate_id": str(world.other_candidate.id)},
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert str(world.application.id) in ids
    assert str(world.other_application.id) not in ids
