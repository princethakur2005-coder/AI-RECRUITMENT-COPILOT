from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.schemas.saved_filters import (
    SavedFilterCreate,
    SavedFilterFilter,
    SavedFilterListResponse,
    SavedFilterResponse,
    SavedFilterUpdate,
)


class SavedFiltersService:
    """Generic in-memory saved filter registry for search workflows."""

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._items: dict[UUID, SavedFilterResponse] = {}
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def save_filter(self, payload: SavedFilterCreate) -> SavedFilterResponse:
        now = self._now_provider()
        item = SavedFilterResponse(
            id=uuid4(),
            owner_id=payload.owner_id,
            name=payload.name,
            category=payload.category,
            entity_type=payload.entity_type,
            filters=dict(payload.filters or {}),
            query=payload.query,
            metadata=dict(payload.metadata or {}),
            is_default=bool(payload.is_default),
            created_at=now,
            updated_at=now,
        )

        self._items[item.id] = item
        if item.is_default:
            self._unset_other_defaults(owner_id=item.owner_id, category=item.category, entity_type=item.entity_type, except_id=item.id)
        return item

    def create_filter(self, payload: SavedFilterCreate) -> SavedFilterResponse:
        return self.save_filter(payload)

    def get_filter(self, filter_id: UUID, owner_id: UUID | str | None = None) -> SavedFilterResponse | None:
        item = self._items.get(filter_id)
        if item is None:
            return None
        if owner_id is not None and item.owner_id != owner_id:
            return None
        return item

    def update_filter(
        self,
        filter_id: UUID,
        payload: SavedFilterUpdate,
        owner_id: UUID | str | None = None,
    ) -> SavedFilterResponse | None:
        item = self.get_filter(filter_id=filter_id, owner_id=owner_id)
        if item is None:
            return None

        if payload.name is not None:
            item.name = payload.name
        if payload.category is not None:
            item.category = payload.category
        if payload.entity_type is not None:
            item.entity_type = payload.entity_type
        if payload.filters is not None:
            item.filters = dict(payload.filters)
        if payload.query is not None:
            item.query = payload.query
        if payload.metadata is not None:
            merged_metadata = dict(item.metadata or {})
            merged_metadata.update(payload.metadata)
            item.metadata = merged_metadata
        if payload.is_default is not None:
            item.is_default = bool(payload.is_default)

        item.updated_at = self._now_provider()

        if item.is_default:
            self._unset_other_defaults(owner_id=item.owner_id, category=item.category, entity_type=item.entity_type, except_id=item.id)

        return item

    def delete_filter(self, filter_id: UUID, owner_id: UUID | str | None = None) -> bool:
        item = self.get_filter(filter_id=filter_id, owner_id=owner_id)
        if item is None:
            return False
        del self._items[filter_id]
        return True

    def remove_filter(self, filter_id: UUID, owner_id: UUID | str | None = None) -> bool:
        return self.delete_filter(filter_id=filter_id, owner_id=owner_id)

    def list_filters(self, filters: SavedFilterFilter | None = None) -> SavedFilterListResponse:
        query = filters or SavedFilterFilter()
        records = list(self._items.values())
        records = [item for item in records if self._matches(item, query)]
        records.sort(key=lambda item: item.updated_at, reverse=True)

        total = len(records)
        paged = records[query.offset : query.offset + query.limit]
        return SavedFilterListResponse(items=paged, total=total)

    def list_saved_filters(self, filters: SavedFilterFilter | None = None) -> SavedFilterListResponse:
        return self.list_filters(filters=filters)

    def set_default_filter(
        self,
        filter_id: UUID,
        owner_id: UUID | str | None = None,
    ) -> SavedFilterResponse | None:
        item = self.get_filter(filter_id=filter_id, owner_id=owner_id)
        if item is None:
            return None

        item.is_default = True
        item.updated_at = self._now_provider()
        self._unset_other_defaults(owner_id=item.owner_id, category=item.category, entity_type=item.entity_type, except_id=item.id)
        return item

    def clear_default_filter(
        self,
        filter_id: UUID,
        owner_id: UUID | str | None = None,
    ) -> SavedFilterResponse | None:
        item = self.get_filter(filter_id=filter_id, owner_id=owner_id)
        if item is None:
            return None

        item.is_default = False
        item.updated_at = self._now_provider()
        return item

    def _unset_other_defaults(
        self,
        *,
        owner_id: UUID | str,
        category,
        entity_type: str | None,
        except_id: UUID,
    ) -> None:
        now = self._now_provider()
        for other in self._items.values():
            if other.id == except_id:
                continue
            if other.owner_id != owner_id:
                continue
            if other.category != category:
                continue
            if other.entity_type != entity_type:
                continue
            if other.is_default:
                other.is_default = False
                other.updated_at = now

    def _matches(self, item: SavedFilterResponse, filters: SavedFilterFilter) -> bool:
        if filters.owner_id is not None and item.owner_id != filters.owner_id:
            return False
        if filters.category is not None and item.category != filters.category:
            return False
        if filters.entity_type is not None and item.entity_type != filters.entity_type:
            return False
        if filters.is_default is not None and item.is_default != filters.is_default:
            return False
        return True


saved_filters_service = SavedFiltersService()
