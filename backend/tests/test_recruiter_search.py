"""PostgreSQL-backed recruiter search foundation."""

from __future__ import annotations

from collections.abc import Callable
from json import dumps

import pytest
from fastapi.testclient import TestClient

from app.core.application_status import ApplicationStatus
from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.jwt import create_access_token
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.job import Job
from app.models.user import User
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]

_HIT_KEYS = {
    "entity_type",
    "entity_id",
    "title",
    "subtitle",
    "status",
    "job_id",
    "candidate_id",
    "application_id",
}
_FORBIDDEN_SUBSTRINGS = (
    "hashed_password",
    "recruiter_notes",
    "resume_path",
    "job_intelligence",
    "ai_hiring_summary",
    "decision_detail",
    "recruiter_override",
    "recruiter_metadata",
    "overall_score",
)


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


def _create_job(world: OfferWorld, title: str, *, company: Company | None = None, member: CompanyMember | None = None, created_by: User | None = None) -> Job:
    job = Job(
        company_id=(company or world.company).id,
        company_member_id=(member or world.recruiter_member).id,
        created_by_id=(created_by or world.recruiter).id,
        title=title,
        status="open",
        is_active=True,
        openings=1,
    )
    world.db.add(job)
    world.db.flush()
    return job


def _create_candidate(world: OfferWorld, email: str, name: str) -> Candidate:
    parts = name.split(" ", 1)
    candidate = Candidate(
        first_name=parts[0],
        last_name=parts[1] if len(parts) > 1 else "Candidate",
        full_name=name,
        email=email,
        status="new",
        is_active=True,
    )
    world.db.add(candidate)
    world.db.flush()
    return candidate


def _create_application(world: OfferWorld, job: Job, candidate: Candidate, *, company: Company | None = None, status: str = ApplicationStatus.APPLIED.value) -> Application:
    application = Application(
        company_id=(company or world.company).id,
        job_id=job.id,
        candidate_id=candidate.id,
        status=status,
        source="test",
    )
    world.db.add(application)
    world.db.flush()
    return application


def _search(client: TestClient, q: str, **params):
    return client.get("/search", params={"q": q, **params})


def test_candidate_search_within_company(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "Ada", types="candidate").json()
    assert payload["candidate_total"] == 1
    assert payload["total"] == 1
    hit = payload["items"][0]
    assert hit["entity_type"] == "candidate"
    assert hit["entity_id"] == str(world.candidate.id)
    assert hit["title"] == "Ada Lovelace"
    assert hit["subtitle"] == "candidate@example.com"
    assert hit["status"] == "new"
    assert hit["candidate_id"] == str(world.candidate.id)
    assert hit["application_id"] is None


def test_job_search_within_company(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "Backend", types="job").json()
    assert payload["job_total"] == 1
    hit = payload["items"][0]
    assert hit["entity_type"] == "job"
    assert hit["entity_id"] == str(world.job.id)
    assert hit["title"] == "Backend Engineer"
    assert hit["status"] == "open"
    assert hit["job_id"] == str(world.job.id)


def test_application_search_within_company(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "Ada", types="application").json()
    assert payload["application_total"] == 1
    hit = payload["items"][0]
    assert hit["entity_type"] == "application"
    assert hit["entity_id"] == str(world.application.id)
    assert hit["title"] == "Ada Lovelace"
    assert hit["subtitle"] == "Backend Engineer"
    assert hit["status"] == ApplicationStatus.INTERVIEW.value
    assert hit["application_id"] == str(world.application.id)
    assert hit["candidate_id"] == str(world.candidate.id)
    assert hit["job_id"] == str(world.job.id)


def test_unified_search_returns_candidates_then_jobs_then_applications(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "Ada").json()
    types = [item["entity_type"] for item in payload["items"]]
    assert types == ["candidate", "application"]
    assert payload["candidate_total"] == 1
    assert payload["job_total"] == 0
    assert payload["application_total"] == 1


def test_cross_company_records_are_never_returned(api_client, world: OfferWorld) -> None:
    acme = _search(api_client(world.recruiter), "Other").json()
    assert acme["total"] == 0
    assert acme["items"] == []

    other = _search(api_client(world.other_recruiter), "Ada").json()
    assert other["total"] == 0
    ids = {item["entity_id"] for item in other["items"]}
    assert str(world.candidate.id) not in ids
    assert str(world.application.id) not in ids
    assert str(world.job.id) not in ids

    ignored = _search(
        api_client(world.recruiter),
        "Other",
        company_id=str(world.other_company.id),
    ).json()
    assert ignored["total"] == 0


def test_candidate_jwt_cannot_access_recruiter_search(candidate_api_client, world: OfferWorld) -> None:
    response = candidate_api_client(world.candidate).get("/search", params={"q": "Ada"})
    assert response.status_code == 401


def test_unauthenticated_search_is_rejected(world: OfferWorld) -> None:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = TestClient(app).get("/search", params={"q": "Ada"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_interviewer_cannot_search(api_client, world: OfferWorld) -> None:
    assert _search(api_client(world.viewer), "Ada").status_code == 403


def test_hiring_manager_can_search(api_client, world: OfferWorld) -> None:
    response = _search(api_client(world.hiring_manager), "Ada", types="candidate")
    assert response.status_code == 200
    assert response.json()["candidate_total"] == 1


def test_pagination_is_deterministic(api_client, world: OfferWorld) -> None:
    _create_job(world, "Zephyr SearchSlot A")
    _create_job(world, "Zephyr SearchSlot B")
    _create_job(world, "Zephyr SearchSlot C")
    world.db.commit()

    first = _search(api_client(world.recruiter), "Zephyr SearchSlot", types="job", offset=0, limit=2).json()
    second = _search(api_client(world.recruiter), "Zephyr SearchSlot", types="job", offset=2, limit=2).json()
    assert first["job_total"] == 3
    assert [item["title"] for item in first["items"]] == ["Zephyr SearchSlot A", "Zephyr SearchSlot B"]
    assert [item["title"] for item in second["items"]] == ["Zephyr SearchSlot C"]
    assert {item["entity_id"] for item in first["items"]}.isdisjoint({item["entity_id"] for item in second["items"]})

    concatenated_first = _search(api_client(world.recruiter), "Ada", offset=0, limit=1).json()
    concatenated_second = _search(api_client(world.recruiter), "Ada", offset=1, limit=1).json()
    assert concatenated_first["items"][0]["entity_type"] == "candidate"
    assert concatenated_second["items"][0]["entity_type"] == "application"


def test_empty_and_short_queries_are_safe(api_client, world: OfferWorld) -> None:
    empty = _search(api_client(world.recruiter), "").json()
    short = _search(api_client(world.recruiter), "A").json()
    wildcard = _search(api_client(world.recruiter), "%").json()
    underscore = _search(api_client(world.recruiter), "_").json()
    escaped = _search(api_client(world.recruiter), "%Ada").json()
    for payload in (empty, short, wildcard, underscore, escaped):
        assert payload["total"] == 0
        assert payload["items"] == []


def test_search_does_not_expose_restricted_fields(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "Ada").json()
    serialized = dumps(payload)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in serialized
    for item in payload["items"]:
        assert set(item.keys()) <= _HIT_KEYS
        assert "email" not in item
        assert "phone" not in item
        assert "skills" not in item
        assert "summary" not in item
        assert "description" not in item


def test_email_search_finds_candidate(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "candidate@example.com", types="candidate").json()
    assert payload["candidate_total"] == 1
    assert payload["items"][0]["entity_id"] == str(world.candidate.id)


def test_application_status_search(api_client, world: OfferWorld) -> None:
    payload = _search(api_client(world.recruiter), "interview", types="application").json()
    assert payload["application_total"] == 1
    assert payload["items"][0]["entity_id"] == str(world.application.id)


def test_existing_job_application_candidate_reads_unaffected(api_client, world: OfferWorld) -> None:
    client = api_client(world.recruiter)
    jobs = client.get("/jobs")
    job = client.get(f"/jobs/{world.job.id}")
    application = client.get(f"/applications/{world.application.id}")
    pipeline = client.get(f"/jobs/{world.job.id}/applications")
    assert jobs.status_code == 200
    assert any(item["id"] == str(world.job.id) for item in jobs.json())
    assert job.status_code == 200
    assert job.json()["title"] == "Backend Engineer"
    assert application.status_code == 200
    assert application.json()["id"] == str(world.application.id)
    assert pipeline.status_code == 200
    assert any(item["id"] == str(world.application.id) for item in pipeline.json())
