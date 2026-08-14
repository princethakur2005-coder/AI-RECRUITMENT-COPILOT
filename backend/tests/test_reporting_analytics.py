"""Reports & analytics foundation — tenant-safe read aggregations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.application_status import ApplicationStatus, PIPELINE_STATUSES
from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType
from app.core.jwt import create_access_token
from app.core.offer_status import OfferStatus
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.application import Application
from app.models.branch import Branch
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.interview import Interview
from app.models.job import Job
from app.models.offer import Offer
from app.models.user import User
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


def _utc(*parts: int) -> datetime:
    year, month, day = parts[0], parts[1], parts[2]
    hour = parts[3] if len(parts) > 3 else 12
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


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


def _create_branch(world: OfferWorld, company: Company, name: str, slug: str) -> Branch:
    branch = Branch(company_id=company.id, name=name, slug=slug, is_active=True)
    world.db.add(branch)
    world.db.flush()
    return branch


def _create_job(
    world: OfferWorld,
    *,
    title: str,
    branch: Branch | None = None,
    company: Company | None = None,
    member: CompanyMember | None = None,
    created_by: User | None = None,
) -> Job:
    job = Job(
        company_id=(company or world.company).id,
        company_member_id=(member or world.recruiter_member).id,
        created_by_id=(created_by or world.recruiter).id,
        branch_id=branch.id if branch is not None else None,
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


def _create_application(
    world: OfferWorld,
    job: Job,
    candidate: Candidate,
    *,
    status: str,
    applied_at: datetime | None = None,
    updated_at: datetime | None = None,
    company: Company | None = None,
) -> Application:
    now = datetime.now(timezone.utc)
    application = Application(
        company_id=(company or world.company).id,
        job_id=job.id,
        candidate_id=candidate.id,
        status=status,
        source="test",
        applied_at=applied_at or now,
        updated_at=updated_at or applied_at or now,
    )
    world.db.add(application)
    world.db.flush()
    return application


def _create_interview(
    world: OfferWorld,
    application: Application,
    *,
    status: str,
    scheduled_start: datetime,
    company: Company | None = None,
    member: CompanyMember | None = None,
) -> Interview:
    interview = Interview(
        application_id=application.id,
        company_id=(company or world.company).id,
        interviewer_member_id=(member or world.recruiter_member).id,
        interview_type=InterviewType.TECHNICAL.value,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_start + timedelta(hours=1),
        timezone="UTC",
        status=status,
    )
    world.db.add(interview)
    world.db.flush()
    return interview


def _create_offer(
    world: OfferWorld,
    application: Application,
    *,
    status: str,
    created_at: datetime | None = None,
) -> Offer:
    now = datetime.now(timezone.utc)
    offer = Offer(
        application_id=application.id,
        candidate_id=application.candidate_id,
        job_id=application.job_id,
        revision=1,
        is_active=True,
        status=status,
        created_at=created_at or now,
        updated_at=created_at or now,
    )
    world.db.add(offer)
    world.db.flush()
    return offer


def _seed_reporting_dataset(world: OfferWorld) -> dict:
    hq = _create_branch(world, world.company, "HQ", "hq")
    remote = _create_branch(world, world.company, "Remote", "remote")
    world.job.branch_id = hq.id

    remote_job = _create_job(world, title="Remote Analyst", branch=remote)
    screening_candidate = _create_candidate(world, "screen@acme.test", "Screen Candidate")
    hired_candidate = _create_candidate(world, "hired@acme.test", "Hired Candidate")
    remote_candidate = _create_candidate(world, "remote@acme.test", "Remote Candidate")

    early = _utc(2026, 1, 10)
    mid = _utc(2026, 2, 15)
    late = _utc(2026, 3, 20)

    world.application.status = ApplicationStatus.INTERVIEW.value
    world.application.applied_at = early
    world.application.updated_at = early

    screening = _create_application(
        world,
        world.job,
        screening_candidate,
        status=ApplicationStatus.SCREENING.value,
        applied_at=mid,
    )
    hired = _create_application(
        world,
        world.job,
        hired_candidate,
        status=ApplicationStatus.HIRED.value,
        applied_at=late,
        updated_at=late,
    )
    remote_app = _create_application(
        world,
        remote_job,
        remote_candidate,
        status=ApplicationStatus.APPLIED.value,
        applied_at=mid,
    )

    scheduled = _create_interview(
        world,
        world.application,
        status=InterviewStatus.SCHEDULED.value,
        scheduled_start=mid,
    )
    completed = _create_interview(
        world,
        hired,
        status=InterviewStatus.COMPLETED.value,
        scheduled_start=late,
    )
    remote_interview = _create_interview(
        world,
        remote_app,
        status=InterviewStatus.SCHEDULED.value,
        scheduled_start=late,
    )

    draft_offer = _create_offer(
        world,
        world.application,
        status=OfferStatus.DRAFT.value,
        created_at=mid,
    )
    accepted_offer = _create_offer(
        world,
        hired,
        status=OfferStatus.ACCEPTED.value,
        created_at=late,
    )

    world.db.commit()
    return {
        "hq": hq,
        "remote": remote,
        "remote_job": remote_job,
        "screening": screening,
        "hired": hired,
        "remote_app": remote_app,
        "scheduled": scheduled,
        "completed": completed,
        "remote_interview": remote_interview,
        "draft_offer": draft_offer,
        "accepted_offer": accepted_offer,
    }


def test_company_scoped_overview_metrics(api_client, world: OfferWorld) -> None:
    seeded = _seed_reporting_dataset(world)
    payload = api_client(world.recruiter).get("/dashboard/analytics/overview").json()

    assert payload["company_id"] == str(world.company.id)
    assert payload["total_jobs"] == 2
    assert payload["active_jobs"] == 2
    assert payload["total_applications"] == 4
    assert payload["applications_by_status"][ApplicationStatus.INTERVIEW.value] == 1
    assert payload["applications_by_status"][ApplicationStatus.SCREENING.value] == 1
    assert payload["applications_by_status"][ApplicationStatus.HIRED.value] == 1
    assert payload["applications_by_status"][ApplicationStatus.APPLIED.value] == 1
    assert payload["interviews_scheduled"] == 2
    assert payload["interviews_completed"] == 1
    assert payload["offers_created"] == 2
    assert payload["offers_accepted"] == 1
    assert payload["hires"] == 1
    assert seeded["hq"].id is not None


def test_cross_company_access_is_blocked(api_client, world: OfferWorld) -> None:
    seeded = _seed_reporting_dataset(world)
    other = api_client(world.other_recruiter).get("/dashboard/analytics/overview")
    assert other.status_code == 200
    payload = other.json()
    assert payload["company_id"] == str(world.other_company.id)
    assert payload["total_applications"] == 1
    assert payload["hires"] == 0
    assert payload["offers_created"] == 0

    leaked = api_client(world.other_recruiter).get(
        f"/dashboard/analytics/overview?branch_id={seeded['hq'].id}",
    )
    assert leaked.status_code == 404

    job_leak = api_client(world.other_recruiter).get(f"/jobs/{world.job.id}/analytics")
    assert job_leak.status_code == 404


def test_branch_filtering_works(api_client, world: OfferWorld) -> None:
    seeded = _seed_reporting_dataset(world)
    hq = api_client(world.recruiter).get(
        f"/dashboard/analytics/overview?branch_id={seeded['hq'].id}",
    ).json()
    remote = api_client(world.recruiter).get(
        f"/dashboard/analytics/overview?branch_id={seeded['remote'].id}",
    ).json()

    assert hq["total_jobs"] == 1
    assert hq["total_applications"] == 3
    assert hq["interviews_scheduled"] == 1
    assert hq["interviews_completed"] == 1
    assert hq["offers_created"] == 2
    assert hq["hires"] == 1

    assert remote["total_jobs"] == 1
    assert remote["total_applications"] == 1
    assert remote["applications_by_status"][ApplicationStatus.APPLIED.value] == 1
    assert remote["interviews_scheduled"] == 1
    assert remote["offers_created"] == 0
    assert remote["hires"] == 0


def test_job_level_analytics_are_scoped(api_client, world: OfferWorld) -> None:
    seeded = _seed_reporting_dataset(world)
    own = api_client(world.recruiter).get(f"/jobs/{world.job.id}/analytics")
    assert own.status_code == 200, own.text
    payload = own.json()
    assert payload["job_id"] == str(world.job.id)
    assert payload["company_id"] == str(world.company.id)
    assert payload["branch_id"] == str(seeded["hq"].id)
    assert payload["applications"] == 3
    assert payload["interviews"] == 2
    assert payload["offers"] == 2
    assert payload["hires"] == 1
    assert payload["pipeline"][ApplicationStatus.HIRED.value] == 1

    remote = api_client(world.recruiter).get(f"/jobs/{seeded['remote_job'].id}/analytics").json()
    assert remote["applications"] == 1
    assert remote["interviews"] == 1
    assert remote["offers"] == 0
    assert remote["hires"] == 0

    foreign = api_client(world.recruiter).get(f"/jobs/{world.other_job.id}/analytics")
    assert foreign.status_code == 404


def test_application_status_counts_are_complete(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    pipeline = api_client(world.recruiter).get("/dashboard/analytics/pipeline").json()
    statuses = pipeline["applications_by_status"]
    assert set(statuses) == {status.value for status in PIPELINE_STATUSES}
    assert statuses[ApplicationStatus.REJECTED.value] == 0
    assert statuses[ApplicationStatus.OFFERED.value] == 0
    assert statuses[ApplicationStatus.SHORTLISTED.value] == 0


def test_interview_metrics_are_correct(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    pipeline = api_client(world.recruiter).get("/dashboard/analytics/pipeline").json()
    interviews = pipeline["interviews_by_status"]
    assert interviews[InterviewStatus.SCHEDULED.value] == 2
    assert interviews[InterviewStatus.COMPLETED.value] == 1
    assert interviews[InterviewStatus.CANCELLED.value] == 0
    assert interviews[InterviewStatus.NO_SHOW.value] == 0


def test_offer_metrics_are_correct(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    pipeline = api_client(world.recruiter).get("/dashboard/analytics/pipeline").json()
    offers = pipeline["offers_by_status"]
    assert offers[OfferStatus.DRAFT.value] == 1
    assert offers[OfferStatus.ACCEPTED.value] == 1
    assert offers[OfferStatus.PENDING_APPROVAL.value] == 0


def test_hiring_metrics_are_correct(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    overview = api_client(world.recruiter).get("/dashboard/analytics/overview").json()
    assert overview["hires"] == 1
    series = api_client(world.recruiter).get("/dashboard/analytics/time-series").json()
    assert sum(point["count"] for point in series["hires"]) == 1
    assert any(point["period"].startswith("2026-03-20") for point in series["hires"])


def test_date_range_filtering_works(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    payload = api_client(world.recruiter).get(
        "/dashboard/analytics/overview",
        params={
            "date_from": "2026-02-01T00:00:00Z",
            "date_to": "2026-02-28T23:59:59Z",
        },
    ).json()
    assert payload["total_applications"] == 2
    assert payload["applications_by_status"][ApplicationStatus.SCREENING.value] == 1
    assert payload["applications_by_status"][ApplicationStatus.APPLIED.value] == 1
    assert payload["interviews_scheduled"] == 1
    assert payload["interviews_completed"] == 0
    assert payload["offers_created"] == 1
    assert payload["offers_accepted"] == 0
    assert payload["hires"] == 0

    inverted = api_client(world.recruiter).get(
        "/dashboard/analytics/overview",
        params={
            "date_from": "2026-03-01T00:00:00Z",
            "date_to": "2026-01-01T00:00:00Z",
        },
    )
    assert inverted.status_code == 400


def test_empty_datasets_return_zero_results(api_client, world: OfferWorld) -> None:
    empty_owner = User(
        full_name="Empty Owner",
        email=f"empty-owner-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        role="user",
        is_active=True,
    )
    world.db.add(empty_owner)
    world.db.flush()
    empty_company = Company(
        name="Empty Co",
        slug=f"empty-{uuid4().hex[:8]}",
        owner_id=empty_owner.id,
        is_active=True,
    )
    world.db.add(empty_company)
    world.db.flush()
    empty_owner.company_id = empty_company.id
    recruiter = User(
        full_name="Empty Recruiter",
        email=f"empty-rec-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        role="user",
        is_active=True,
        company_id=empty_company.id,
    )
    world.db.add(recruiter)
    world.db.flush()
    world.db.add(
        CompanyMember(
            company_id=empty_company.id,
            user_id=recruiter.id,
            role="recruiter",
            is_active=True,
        )
    )
    world.db.commit()

    overview = api_client(recruiter).get("/dashboard/analytics/overview").json()
    assert overview["total_jobs"] == 0
    assert overview["active_jobs"] == 0
    assert overview["total_applications"] == 0
    assert overview["interviews_scheduled"] == 0
    assert overview["offers_created"] == 0
    assert overview["hires"] == 0
    assert all(count == 0 for count in overview["applications_by_status"].values())

    pipeline = api_client(recruiter).get("/dashboard/analytics/pipeline").json()
    assert all(count == 0 for count in pipeline["applications_by_status"].values())
    assert all(count == 0 for count in pipeline["interviews_by_status"].values())
    assert all(count == 0 for count in pipeline["offers_by_status"].values())

    series = api_client(recruiter).get("/dashboard/analytics/time-series").json()
    assert series["applications"] == []
    assert series["interviews"] == []
    assert series["hires"] == []


def test_no_nplus_one_entity_loading(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    statements: list[str] = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:  # noqa: ANN001
        statements.append(str(statement))

    engine = world.db.get_bind()
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        response = api_client(world.recruiter).get("/dashboard/analytics/overview")
        assert response.status_code == 200
        api_client(world.recruiter).get("/dashboard/analytics/pipeline")
        api_client(world.recruiter).get("/dashboard/analytics/time-series")
        api_client(world.recruiter).get(f"/jobs/{world.job.id}/analytics")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(statements) < 40
    joined = "\n".join(statements).lower()
    assert "count(" in joined
    assert "group by" in joined
    for statement in statements:
        compact = " ".join(statement.lower().split())
        if compact.startswith("select applications.") and "count(" not in compact:
            pytest.fail(f"Loaded application rows instead of aggregating: {statement}")
        if compact.startswith("select interviews.") and "count(" not in compact:
            pytest.fail(f"Loaded interview rows instead of aggregating: {statement}")
        if compact.startswith("select offers.") and "count(" not in compact:
            pytest.fail(f"Loaded offer rows instead of aggregating: {statement}")


def test_candidate_cannot_access_staff_analytics(candidate_api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    client = candidate_api_client(world.candidate)
    assert client.get("/dashboard/analytics/overview").status_code == 401
    assert client.get("/dashboard/analytics/pipeline").status_code == 401
    assert client.get("/dashboard/analytics/time-series").status_code == 401
    assert client.get(f"/jobs/{world.job.id}/analytics").status_code == 401


def test_interviewer_cannot_access_analytics(api_client, world: OfferWorld) -> None:
    response = api_client(world.viewer).get("/dashboard/analytics/overview")
    assert response.status_code == 403


def test_time_series_counts_match_seeded_days(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    series = api_client(world.recruiter).get("/dashboard/analytics/time-series").json()
    applications = {point["period"][:10]: point["count"] for point in series["applications"]}
    interviews = {point["period"][:10]: point["count"] for point in series["interviews"]}
    assert applications["2026-01-10"] == 1
    assert applications["2026-02-15"] == 2
    assert applications["2026-03-20"] == 1
    assert interviews["2026-02-15"] == 1
    assert interviews["2026-03-20"] == 2


def test_existing_dashboard_overview_still_works(api_client, world: OfferWorld) -> None:
    _seed_reporting_dataset(world)
    response = api_client(world.recruiter).get("/dashboard")
    assert response.status_code == 200
    stats = response.json()["stats"]
    assert stats["total_jobs"] == 2
    assert stats["total_applications"] == 4
    assert stats["hired"] == 1
