from __future__ import annotations

from uuid import UUID

DASHBOARD_CACHE_NAMESPACE = "dashboard"


def dashboard_cache_prefix(company_id: UUID) -> str:
    return f"{DASHBOARD_CACHE_NAMESPACE}:{company_id}:"


def dashboard_cache_key(company_id: UUID, view: str) -> str:
    return f"{dashboard_cache_prefix(company_id)}{view}"
