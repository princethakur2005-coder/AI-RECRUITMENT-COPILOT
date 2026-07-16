from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from app.schemas.global_search import (
    GlobalSearchRequest,
    GlobalSearchResponse,
    SearchEntityType,
    SearchPagination,
    SearchResultGroup,
    SearchResultItem,
)


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        entity_type: SearchEntityType,
        filters: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[SearchResultItem]:
        ...


class InMemorySearchProvider:
    """Simple provider adapter for lists of dictionaries."""

    def __init__(self, data_loader: Callable[[], list[dict[str, Any]]]) -> None:
        self._data_loader = data_loader

    def search(
        self,
        query: str,
        *,
        entity_type: SearchEntityType,
        filters: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[SearchResultItem]:
        records = list(self._data_loader() or [])
        effective_filters = dict(filters or {})
        q = (query or "").strip().lower()

        results: list[SearchResultItem] = []
        for record in records:
            if not self._matches_filters(record, effective_filters):
                continue

            title = str(record.get("title") or record.get("name") or record.get("email") or "")
            subtitle = record.get("subtitle")
            snippet = record.get("snippet")
            haystack = " ".join(
                [
                    title,
                    str(subtitle or ""),
                    str(snippet or ""),
                    str(record.get("description") or ""),
                ]
            ).lower()

            if q and q not in haystack:
                continue

            score = 1.0
            if q:
                if q == title.lower():
                    score = 1.0
                elif q in title.lower():
                    score = 0.9
                else:
                    score = 0.75

            results.append(
                SearchResultItem(
                    entity_type=entity_type,
                    entity_id=str(record.get("id") or record.get("entity_id") or ""),
                    title=title or str(record.get("id") or "unknown"),
                    subtitle=str(subtitle) if subtitle is not None else None,
                    snippet=str(snippet) if snippet is not None else None,
                    score=score,
                    metadata={k: v for k, v in record.items() if k not in {"id", "entity_id", "title", "name", "email", "subtitle", "snippet"}},
                    created_at=record.get("created_at"),
                    updated_at=record.get("updated_at"),
                )
            )

        results.sort(key=lambda item: (item.score or 0.0, str(item.title).lower()), reverse=True)
        return results

    def _matches_filters(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if expected is None:
                continue
            if record.get(key) != expected:
                return False
        return True


class GlobalSearchService:
    """Unified provider-agnostic search orchestration service."""

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._providers: dict[SearchEntityType, SearchProvider] = {}
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def register_provider(self, entity_type: SearchEntityType, provider: SearchProvider) -> None:
        self._providers[entity_type] = provider

    def unregister_provider(self, entity_type: SearchEntityType) -> None:
        self._providers.pop(entity_type, None)

    def search(self, request: GlobalSearchRequest) -> GlobalSearchResponse:
        query = request.query or ""
        requested_entities = list(request.entity_types or [])

        grouped: dict[SearchEntityType, list[SearchResultItem]] = {}
        for entity_type in requested_entities:
            provider = self._providers.get(entity_type)
            if provider is None:
                grouped[entity_type] = []
                continue

            entity_filters = self._extract_entity_filters(request.filters, entity_type)
            grouped[entity_type] = provider.search(
                query=query,
                entity_type=entity_type,
                filters=entity_filters,
                options=dict(request.options or {}),
            )

        combined = [item for items in grouped.values() for item in items]
        combined.sort(key=lambda item: (item.score or 0.0, str(item.title).lower()), reverse=True)

        total = len(combined)
        page = request.page
        page_size = request.page_size
        start = (page - 1) * page_size
        end = start + page_size
        paged = combined[start:end]

        total_pages = max(1, math.ceil(total / page_size)) if page_size > 0 else 1
        pagination = SearchPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

        groups: list[SearchResultGroup] = []
        for entity_type in requested_entities:
            group_items = grouped.get(entity_type, [])
            groups.append(
                SearchResultGroup(
                    entity_type=entity_type,
                    total=len(group_items),
                    items=group_items,
                )
            )

        return GlobalSearchResponse(
            query=query,
            items=paged,
            groups=groups,
            pagination=pagination,
            metadata={
                "provider": "global_search_service",
                "generated_at": self._now_provider().isoformat(),
                "registered_entity_types": [et.value for et in self._providers.keys()],
                "extensible_modes": ["keyword", "semantic", "vector"],
            },
        )

    def unified_search(self, request: GlobalSearchRequest) -> GlobalSearchResponse:
        return self.search(request)

    def query(self, request: GlobalSearchRequest) -> GlobalSearchResponse:
        return self.search(request)

    def _extract_entity_filters(self, filters: dict[str, Any], entity_type: SearchEntityType) -> dict[str, Any]:
        if not filters:
            return {}

        shared = dict(filters.get("all") or {})
        entity_specific = dict(filters.get(entity_type.value) or {})
        for key, value in filters.items():
            if key in {"all", SearchEntityType.CANDIDATE.value, SearchEntityType.JOB.value, SearchEntityType.USER.value}:
                continue
            shared[key] = value

        merged = dict(shared)
        merged.update(entity_specific)
        return merged


global_search_service = GlobalSearchService()
