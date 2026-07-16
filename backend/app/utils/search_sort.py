from __future__ import annotations

from typing import Any, Iterable


class QueryParams:
    """Reusable query parameters for filtering, sorting, and pagination."""

    def __init__(self, filters: dict[str, Any] | None = None, sort_by: str | None = None, sort_order: str = "asc", page: int = 1, page_size: int = 20):
        self.filters = filters or {}
        self.sort_by = sort_by
        self.sort_order = sort_order.lower() if sort_order else "asc"
        self.page = max(page, 1)
        self.page_size = max(page_size, 1)


class SearchSortPaginator:
    """Reusable helper for filtering, sorting, and paginating collections."""

    @staticmethod
    def apply(items: Iterable[Any], params: QueryParams) -> dict[str, Any]:
        filtered_items = list(items)

        if params.filters:
            filtered_items = [
                item
                for item in filtered_items
                if all(
                    SearchSortPaginator._matches_filter(item, key, value)
                    for key, value in params.filters.items()
                )
            ]

        if params.sort_by:
            reverse = params.sort_order == "desc"
            filtered_items = sorted(
                filtered_items,
                key=lambda item: SearchSortPaginator._get_sort_value(item, params.sort_by),
                reverse=reverse,
            )

        total = len(filtered_items)
        start = (params.page - 1) * params.page_size
        end = start + params.page_size
        page_items = filtered_items[start:end]

        return {
            "items": page_items,
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
            "pages": (total + params.page_size - 1) // params.page_size if total else 0,
        }

    @staticmethod
    def _matches_filter(item: Any, key: str, value: Any) -> bool:
        item_value = SearchSortPaginator._get_attribute(item, key)
        if item_value is None:
            return False

        if isinstance(value, (list, tuple, set)):
            return item_value in value

        if isinstance(item_value, str):
            return str(value).lower() in item_value.lower()

        return item_value == value

    @staticmethod
    def _get_sort_value(item: Any, key: str) -> Any:
        value = SearchSortPaginator._get_attribute(item, key)
        return value if value is not None else ""

    @staticmethod
    def _get_attribute(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)
