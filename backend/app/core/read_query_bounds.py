"""Shared pagination and filter bounds for production read APIs."""

from __future__ import annotations

from datetime import datetime, timedelta

MAX_READ_OFFSET = 10_000
MAX_NOTIFICATION_LIMIT = 500
MAX_AUDIT_LIMIT = 100
MAX_SEARCH_LIMIT = 50
MAX_SEARCH_QUERY_LENGTH = 200
MAX_AUDIT_FILTER_LENGTH = 100
MAX_REPORTING_DATE_RANGE_DAYS = 366


def clamp_offset(offset: int) -> int:
    return max(0, min(int(offset), MAX_READ_OFFSET))


def clamp_limit(limit: int, *, maximum: int) -> int:
    return max(1, min(int(limit), maximum))


def normalize_filter_text(
    value: str | None,
    *,
    max_length: int = MAX_AUDIT_FILTER_LENGTH,
) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_length]


def validate_bounded_date_range(
    date_from: datetime | None,
    date_to: datetime | None,
    *,
    max_days: int = MAX_REPORTING_DATE_RANGE_DAYS,
) -> None:
    if date_from is None or date_to is None:
        return
    if date_from > date_to:
        raise ValueError("date_from must be less than or equal to date_to")
    if (date_to - date_from) > timedelta(days=max_days):
        raise ValueError(f"date range must not exceed {max_days} days")
