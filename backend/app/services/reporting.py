from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.core.config import settings
from app.core.interview_status import InterviewStatus
from app.core.offer_status import OfferStatus
from app.core.read_cache import CacheBackend, get_read_cache
from app.core.read_query_bounds import validate_bounded_date_range
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.reporting import ReportingQueryScope, ReportingRepository
from app.schemas.reporting import (
    JobAnalyticsResponse,
    ReportingOverviewResponse,
    ReportingPipelineResponse,
    ReportingTimeSeriesResponse,
    TimeSeriesPoint,
)
from app.services.recruiter_dashboard import DASHBOARD_ALLOWED_ROLES
from app.services.reporting_cache import reporting_cache_key

TModel = TypeVar("TModel", bound=BaseModel)


class ReportingService:
    """Read-only reporting facade. Company scope is derived from membership."""

    def __init__(
        self,
        reporting_repository: ReportingRepository,
        member_repository: CompanyMemberRepository,
        job_repository: JobRepository,
        branch_repository: BranchRepository,
        cache: CacheBackend | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self.reporting_repository = reporting_repository
        self.member_repository = member_repository
        self.job_repository = job_repository
        self.branch_repository = branch_repository
        self._cache = cache
        self._cache_ttl_seconds = cache_ttl_seconds

    def _cache_backend(self) -> CacheBackend:
        return self._cache if self._cache is not None else get_read_cache()

    def _cache_ttl(self) -> int:
        if self._cache_ttl_seconds is not None:
            return self._cache_ttl_seconds
        return int(getattr(settings, "REPORTING_CACHE_TTL_SECONDS", 30))

    def _cached_response(
        self,
        scope: ReportingQueryScope,
        view: str,
        model_cls: type[TModel],
        loader: Callable[[], TModel],
    ) -> TModel:
        if not getattr(settings, "READ_CACHE_ENABLED", True):
            return loader()
        key = reporting_cache_key(
            scope.company_id,
            view,
            branch_id=scope.branch_id,
            job_id=scope.job_id,
            date_from=scope.date_from,
            date_to=scope.date_to,
        )
        cache = self._cache_backend()
        cached = cache.get(key)
        if cached is not None:
            try:
                return model_cls.model_validate(cached)
            except Exception:
                cache.delete(key)
        result = loader()
        try:
            cache.set(key, result.model_dump(mode="json"), ttl=self._cache_ttl())
        except Exception:
            pass
        return result

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in DASHBOARD_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for recruiter analytics")
        return membership

    def _ensure_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _resolve_scope(
        self,
        user: User,
        *,
        branch_id: UUID | None = None,
        job_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        require_job: bool = False,
    ) -> ReportingQueryScope:
        membership = self._resolve_active_membership(user)
        company_id = membership.company_id

        date_from = self._ensure_utc(date_from)
        date_to = self._ensure_utc(date_to)
        validate_bounded_date_range(date_from, date_to)

        if branch_id is not None:
            branch = self.branch_repository.get_by_id(branch_id)
            if branch is None or branch.company_id != company_id:
                raise LookupError("Branch not found for this company")

        if job_id is not None:
            job = self.job_repository.get_by_id_for_company(job_id, company_id)
            if job is None:
                raise LookupError("Job not found")
            if branch_id is not None and job.branch_id != branch_id:
                raise LookupError("Job not found")
        elif require_job:
            raise LookupError("Job not found")

        return ReportingQueryScope(
            company_id=company_id,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )

    def _scope_meta(self, scope: ReportingQueryScope) -> dict:
        return {
            "company_id": scope.company_id,
            "branch_id": scope.branch_id,
            "job_id": scope.job_id,
            "date_from": scope.date_from,
            "date_to": scope.date_to,
            "generated_at": datetime.now(timezone.utc),
        }

    def get_overview(
        self,
        user: User,
        *,
        branch_id: UUID | None = None,
        job_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ReportingOverviewResponse:
        scope = self._resolve_scope(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )

        def _load() -> ReportingOverviewResponse:
            job_counts = self.job_repository.get_job_counts(
                scope.company_id,
                branch_id=scope.branch_id,
                job_id=scope.job_id,
            )
            applications_by_status = self.reporting_repository.count_applications_by_status(scope)
            interview_counts = self.reporting_repository.count_interviews_by_status(scope)
            offer_counts = self.reporting_repository.count_offers_by_status(scope)
            return ReportingOverviewResponse(
                **self._scope_meta(scope),
                total_jobs=job_counts["total"],
                active_jobs=job_counts["active"],
                total_applications=sum(applications_by_status.values()),
                applications_by_status=applications_by_status,
                interviews_scheduled=interview_counts.get(InterviewStatus.SCHEDULED.value, 0),
                interviews_completed=interview_counts.get(InterviewStatus.COMPLETED.value, 0),
                offers_created=sum(offer_counts.values()),
                offers_accepted=offer_counts.get(OfferStatus.ACCEPTED.value, 0),
                hires=self.reporting_repository.count_hires(scope),
            )

        return self._cached_response(scope, "overview", ReportingOverviewResponse, _load)

    def get_pipeline(
        self,
        user: User,
        *,
        branch_id: UUID | None = None,
        job_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ReportingPipelineResponse:
        scope = self._resolve_scope(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )
        return self._cached_response(
            scope,
            "pipeline",
            ReportingPipelineResponse,
            lambda: ReportingPipelineResponse(
                **self._scope_meta(scope),
                applications_by_status=self.reporting_repository.count_applications_by_status(scope),
                interviews_by_status=self.reporting_repository.count_interviews_by_status(scope),
                offers_by_status=self.reporting_repository.count_offers_by_status(scope),
            ),
        )

    def get_time_series(
        self,
        user: User,
        *,
        branch_id: UUID | None = None,
        job_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ReportingTimeSeriesResponse:
        scope = self._resolve_scope(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )
        return self._cached_response(
            scope,
            "timeseries",
            ReportingTimeSeriesResponse,
            lambda: ReportingTimeSeriesResponse(
                **self._scope_meta(scope),
                applications=[
                    TimeSeriesPoint(period=period, count=count)
                    for period, count in self.reporting_repository.applications_over_time(scope)
                ],
                interviews=[
                    TimeSeriesPoint(period=period, count=count)
                    for period, count in self.reporting_repository.interviews_over_time(scope)
                ],
                hires=[
                    TimeSeriesPoint(period=period, count=count)
                    for period, count in self.reporting_repository.hires_over_time(scope)
                ],
            ),
        )

    def get_job_analytics(
        self,
        user: User,
        job_id: UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> JobAnalyticsResponse:
        scope = self._resolve_scope(
            user,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
            require_job=True,
        )
        job = self.job_repository.get_by_id_for_company(job_id, scope.company_id)
        if job is None:
            raise LookupError("Job not found")

        def _load() -> JobAnalyticsResponse:
            pipeline = self.reporting_repository.count_applications_by_status(scope)
            return JobAnalyticsResponse(
                job_id=job_id,
                company_id=scope.company_id,
                branch_id=job.branch_id,
                date_from=scope.date_from,
                date_to=scope.date_to,
                generated_at=datetime.now(timezone.utc),
                applications=sum(pipeline.values()),
                interviews=self.reporting_repository.count_interviews(scope),
                offers=self.reporting_repository.count_offers(scope),
                hires=self.reporting_repository.count_hires(scope),
                pipeline=pipeline,
            )

        return self._cached_response(scope, "job_analytics", JobAnalyticsResponse, _load)
