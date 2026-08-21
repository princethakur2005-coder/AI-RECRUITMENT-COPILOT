"""Production hardening for read-heavy administrative APIs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.jwt import create_access_token
from app.core.read_cache import FailOpenCache, InProcessCacheBackend
from app.core.read_query_bounds import MAX_REPORTING_DATE_RANGE_DAYS
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.reporting import ReportingRepository
from app.services.reporting import ReportingService
from app.services.reporting_cache import reporting_cache_key
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


class _BrokenCache:
    def get(self, key: str) -> Any:
        raise RuntimeError("cache unavailable")

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        raise RuntimeError("cache unavailable")

    def delete(self, key: str) -> bool:
        raise RuntimeError("cache unavailable")

    def delete_prefix(self, prefix: str) -> int:
        raise RuntimeError("cache unavailable")


class _CountingJobRepository(JobRepository):
    def __init__(self, db, world: OfferWorld) -> None:
        super().__init__(db)
        self.world = world
        self.count_calls = 0

    def get_job_counts(self, company_id: UUID, *, branch_id: UUID | None = None, job_id: UUID | None = None):
        self.count_calls += 1
        return super().get_job_counts(company_id, branch_id=branch_id, job_id=job_id)


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


def test_audit_rejects_excessive_offset(api_client, world: OfferWorld) -> None:
    response = api_client(world.recruiter).get("/audit-logs", params={"offset": 10_001})
    assert response.status_code == 400


def test_audit_rejects_excessive_date_range(api_client, world: OfferWorld) -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=MAX_REPORTING_DATE_RANGE_DAYS + 1)
    response = api_client(world.recruiter).get(
        "/audit-logs",
        params={
            "created_after": start.isoformat().replace("+00:00", "Z"),
            "created_before": end.isoformat().replace("+00:00", "Z"),
        },
    )
    assert response.status_code == 400


def test_notification_rejects_excessive_limit(api_client, world: OfferWorld) -> None:
    response = api_client(world.recruiter).get("/notifications", params={"limit": 501})
    assert response.status_code == 400


def test_search_rejects_excessive_query_length(api_client, world: OfferWorld) -> None:
    response = api_client(world.recruiter).get("/search", params={"q": "x" * 201})
    assert response.status_code == 400


def test_search_rejects_excessive_offset(api_client, world: OfferWorld) -> None:
    response = api_client(world.recruiter).get("/search", params={"q": "ac", "offset": 10_001})
    assert response.status_code == 400


def test_reporting_rejects_excessive_date_range(api_client, world: OfferWorld) -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=MAX_REPORTING_DATE_RANGE_DAYS + 1)
    response = api_client(world.recruiter).get(
        "/dashboard/analytics/overview",
        params={
            "date_from": start.isoformat().replace("+00:00", "Z"),
            "date_to": end.isoformat().replace("+00:00", "Z"),
        },
    )
    assert response.status_code == 400


def test_reporting_recovers_from_invalid_cache_payload(world: OfferWorld) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    cache = InProcessCacheBackend(default_ttl=60)
    service = ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        counting_repo,
        BranchRepository(world.db),
        cache=cache,
        cache_ttl_seconds=60,
    )
    poison_key = reporting_cache_key(world.company.id, "overview")
    cache.set(poison_key, {"invalid": "payload"}, ttl=60)

    overview = service.get_overview(world.recruiter)
    assert overview.total_jobs >= 1
    assert counting_repo.count_calls == 1


def test_reporting_cache_failures_fall_back_to_database(world: OfferWorld) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    broken = FailOpenCache(_BrokenCache())
    service = ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        counting_repo,
        BranchRepository(world.db),
        cache=broken,
        cache_ttl_seconds=60,
    )

    overview = service.get_overview(world.recruiter)
    assert overview.total_jobs >= 1
    assert counting_repo.count_calls == 1


def test_candidate_cannot_access_staff_read_surfaces(
    candidate_api_client,
    world: OfferWorld,
) -> None:
    client = candidate_api_client(world.candidate)
    assert client.get("/search", params={"q": "ac"}).status_code == 401
    assert client.get("/audit-logs").status_code == 401
    assert client.get("/dashboard/analytics/overview").status_code == 401
