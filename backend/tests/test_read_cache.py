"""Targeted in-process read cache — reporting and dashboard aggregates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.application_status import ApplicationStatus
from app.core.read_cache import FailOpenCache, InProcessCacheBackend, set_read_cache
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.reporting import ReportingRepository
from app.services.dashboard_cache import dashboard_cache_key
from app.services.recruiter_dashboard import RecruiterDashboardService
from app.services.reporting import ReportingService
from app.services.reporting_cache import invalidate_company_reporting_cache, reporting_cache_key
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
def cache_clock() -> dict[str, float]:
    return {"now": 0.0}


@pytest.fixture(autouse=True)
def isolated_read_cache(cache_clock: dict[str, float]):
    backend = InProcessCacheBackend(
        maxsize=128,
        default_ttl=30,
        clock=lambda: cache_clock["now"],
    )
    set_read_cache(FailOpenCache(backend))
    yield backend
    set_read_cache(None)


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


def _reporting_service(world: OfferWorld, *, cache=None, ttl: int = 30) -> ReportingService:
    return ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        JobRepository(world.db),
        BranchRepository(world.db),
        cache=cache,
        cache_ttl_seconds=ttl,
    )


def _dashboard_service(world: OfferWorld, *, cache=None, ttl: int = 30) -> RecruiterDashboardService:
    return RecruiterDashboardService(
        JobRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
        cache=cache,
        cache_ttl_seconds=ttl,
    )


def test_cache_hit_avoids_repeating_expensive_read(world: OfferWorld) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    service = ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        counting_repo,
        BranchRepository(world.db),
        cache_ttl_seconds=60,
    )

    first = service.get_overview(world.recruiter)
    second = service.get_overview(world.recruiter)

    assert first.total_jobs == second.total_jobs
    assert counting_repo.count_calls == 1


def test_cache_miss_executes_repository_query(world: OfferWorld, cache_clock: dict[str, float]) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    service = ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        counting_repo,
        BranchRepository(world.db),
        cache_ttl_seconds=60,
    )

    service.get_overview(world.recruiter)
    assert counting_repo.count_calls == 1

    cache_clock["now"] = 120.0
    service.get_overview(world.recruiter)
    assert counting_repo.count_calls == 2


def test_ttl_expiration_causes_recomputation(world: OfferWorld, cache_clock: dict[str, float]) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    service = ReportingService(
        ReportingRepository(world.db),
        CompanyMemberRepository(world.db),
        counting_repo,
        BranchRepository(world.db),
        cache_ttl_seconds=10,
    )

    service.get_overview(world.recruiter)
    cache_clock["now"] = 5.0
    service.get_overview(world.recruiter)
    assert counting_repo.count_calls == 1

    cache_clock["now"] = 11.0
    service.get_overview(world.recruiter)
    assert counting_repo.count_calls == 2


def test_company_cache_entries_are_isolated(
    world: OfferWorld,
    isolated_read_cache: InProcessCacheBackend,
) -> None:
    service = _reporting_service(world)
    acme = service.get_overview(world.recruiter)
    other = service.get_overview(world.other_recruiter)

    assert acme.company_id == world.company.id
    assert other.company_id == world.other_company.id
    assert acme.company_id != other.company_id

    poison_key = reporting_cache_key(world.company.id, "overview")
    isolated_read_cache.set(
        poison_key,
        {
            "company_id": str(world.company.id),
            "branch_id": None,
            "job_id": None,
            "date_from": None,
            "date_to": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_jobs": 9999,
            "active_jobs": 9999,
            "total_applications": 9999,
            "applications_by_status": {status.value: 0 for status in ApplicationStatus},
            "interviews_scheduled": 0,
            "interviews_completed": 0,
            "offers_created": 0,
            "offers_accepted": 0,
            "hires": 0,
        },
        ttl=60,
    )

    other_after_poison = service.get_overview(world.other_recruiter)
    assert other_after_poison.total_jobs != 9999

    acme_key = reporting_cache_key(world.company.id, "overview")
    other_key = reporting_cache_key(world.other_company.id, "overview")
    assert acme_key != other_key


def test_different_filters_do_not_collide(world: OfferWorld) -> None:
    service = _reporting_service(world)
    full = service.get_overview(world.recruiter)
    filtered = service.get_overview(
        world.recruiter,
        date_from=datetime(2099, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )

    assert full.total_applications > 0
    assert filtered.total_applications == 0

    full_key = reporting_cache_key(
        world.company.id,
        "overview",
        date_from=None,
        date_to=None,
    )
    filtered_key = reporting_cache_key(
        world.company.id,
        "overview",
        date_from=datetime(2099, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )
    assert full_key != filtered_key


def test_cache_failures_fall_back_to_database(world: OfferWorld) -> None:
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


def test_mutations_invalidate_cached_reporting_results(api_client, world: OfferWorld) -> None:
    client = api_client(world.recruiter)
    before = client.get("/dashboard/analytics/overview").json()
    assert before["applications_by_status"][ApplicationStatus.REJECTED.value] == 0

    response = client.patch(
        f"/applications/{world.application.id}/status",
        json={"status": ApplicationStatus.REJECTED.value},
    )
    assert response.status_code == 200

    after = client.get("/dashboard/analytics/overview").json()
    assert after["applications_by_status"][ApplicationStatus.REJECTED.value] == 1


def test_mutations_invalidate_cached_dashboard_stats(api_client, world: OfferWorld) -> None:
    client = api_client(world.recruiter)
    before = client.get("/dashboard/stats").json()
    assert before["rejected"] == 0

    response = client.patch(
        f"/applications/{world.application.id}/status",
        json={"status": ApplicationStatus.REJECTED.value},
    )
    assert response.status_code == 200

    after = client.get("/dashboard/stats").json()
    assert after["rejected"] == 1


def test_authorization_is_evaluated_independently_of_cache(world: OfferWorld) -> None:
    service = _reporting_service(world)
    service.get_overview(world.recruiter)

    with pytest.raises(PermissionError):
        service.get_overview(world.viewer)


def test_dashboard_stats_cache_hit(world: OfferWorld) -> None:
    counting_repo = _CountingJobRepository(world.db, world)
    service = RecruiterDashboardService(
        counting_repo,
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
        cache_ttl_seconds=60,
    )

    first = service.get_stats(world.recruiter)
    second = service.get_stats(world.recruiter)

    assert first.total_jobs == second.total_jobs
    assert counting_repo.count_calls == 1


def test_dashboard_cache_keys_are_company_scoped(world: OfferWorld) -> None:
    assert dashboard_cache_key(world.company.id, "stats") != dashboard_cache_key(
        world.other_company.id,
        "stats",
    )


def test_invalidate_clears_reporting_and_dashboard_prefixes(
    world: OfferWorld,
    isolated_read_cache: InProcessCacheBackend,
) -> None:
    reporting_key = reporting_cache_key(world.company.id, "overview")
    dashboard_key = dashboard_cache_key(world.company.id, "stats")
    isolated_read_cache.set(reporting_key, {"total_jobs": 99}, ttl=60)
    isolated_read_cache.set(dashboard_key, {"total_jobs": 99}, ttl=60)

    invalidate_company_reporting_cache(world.company.id)

    assert isolated_read_cache.get(reporting_key) is None
    assert isolated_read_cache.get(dashboard_key) is None
