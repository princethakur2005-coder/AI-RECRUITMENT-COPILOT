from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.read_cache import get_read_cache
from app.services.dashboard_cache import dashboard_cache_prefix

REPORTING_CACHE_NAMESPACE = "reporting"


def _dim(value: UUID | datetime | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.isoformat()
    return str(value)


def reporting_cache_prefix(company_id: UUID) -> str:
    return f"{REPORTING_CACHE_NAMESPACE}:{company_id}:"


def reporting_cache_key(
    company_id: UUID,
    view: str,
    *,
    branch_id: UUID | None = None,
    job_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> str:
    return (
        f"{reporting_cache_prefix(company_id)}{view}"
        f":branch={_dim(branch_id)}"
        f":job={_dim(job_id)}"
        f":from={_dim(date_from)}"
        f":to={_dim(date_to)}"
    )


def invalidate_company_reporting_cache(company_id: UUID) -> None:
    """Drop cached reporting and dashboard aggregates for one company. Fail-open."""
    cache = get_read_cache()
    cache.delete_prefix(reporting_cache_prefix(company_id))
    cache.delete_prefix(dashboard_cache_prefix(company_id))
