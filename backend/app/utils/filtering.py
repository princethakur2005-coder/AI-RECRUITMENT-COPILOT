from __future__ import annotations

from typing import Any, Callable


def filter_by_fields(items: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    if not filters:
        return items

    filtered_items = items
    for key, value in filters.items():
        if value is None:
            continue
        filtered_items = [item for item in filtered_items if item.get(key) == value]

    return filtered_items


def search_items(items: list[dict[str, Any]], query: str, fields: list[str]) -> list[dict[str, Any]]:
    if not query:
        return items

    query_lower = query.lower()
    return [
        item
        for item in items
        if any(str(item.get(field, "")).lower().find(query_lower) >= 0 for field in fields)
    ]
