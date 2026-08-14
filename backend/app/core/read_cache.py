from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol


class CacheBackend(Protocol):
    """Replaceable cache boundary. A Redis backend can implement this later."""

    def get(self, key: str) -> Any | None:
        ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ...

    def delete(self, key: str) -> bool:
        ...

    def delete_prefix(self, prefix: str) -> int:
        ...


class InProcessCacheBackend:
    """Thread-safe process-local TTL cache. Not shared across processes."""

    def __init__(
        self,
        *,
        maxsize: int = 2048,
        default_ttl: int = 30,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.maxsize = max(1, maxsize)
        self.default_ttl = max(1, default_ttl)
        self._clock = clock or __import__("time").monotonic
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _now(self) -> float:
        return float(self._clock())

    def _expired(self, expires_at: float) -> bool:
        return expires_at <= self._now()

    def _prune_locked(self) -> None:
        now = self._now()
        expired = [key for key, (expires_at, _) in self._store.items() if expires_at <= now]
        for key in expired:
            self._store.pop(key, None)
        overflow = len(self._store) - self.maxsize
        if overflow > 0:
            oldest = sorted(self._store.items(), key=lambda item: item[1][0])[:overflow]
            for key, _ in oldest:
                self._store.pop(key, None)

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if self._expired(expires_at):
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl_seconds = self.default_ttl if ttl is None else max(0, int(ttl))
        with self._lock:
            if ttl_seconds == 0:
                self._store.pop(key, None)
                return
            self._prune_locked()
            if len(self._store) >= self.maxsize and key not in self._store:
                self._prune_locked()
                if len(self._store) >= self.maxsize:
                    oldest_key = min(self._store.items(), key=lambda item: item[1][0])[0]
                    self._store.pop(oldest_key, None)
            self._store[key] = (self._now() + ttl_seconds, value)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._store if key.startswith(prefix)]
            for key in keys:
                self._store.pop(key, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class FailOpenCache:
    """Cache failures never block the caller; reads miss and writes are ignored."""

    def __init__(self, backend: CacheBackend) -> None:
        self._backend = backend

    def get(self, key: str) -> Any | None:
        try:
            return self._backend.get(key)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            self._backend.set(key, value, ttl)
        except Exception:
            return

    def delete(self, key: str) -> bool:
        try:
            return bool(self._backend.delete(key))
        except Exception:
            return False

    def delete_prefix(self, prefix: str) -> int:
        try:
            return int(self._backend.delete_prefix(prefix))
        except Exception:
            return 0


class DisabledCache:
    """Always-miss backend used when read caching is turned off."""

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        return None

    def delete(self, key: str) -> bool:
        return False

    def delete_prefix(self, prefix: str) -> int:
        return 0


_read_cache: CacheBackend | None = None


def build_read_cache() -> CacheBackend:
    from app.core.config import settings

    if not getattr(settings, "READ_CACHE_ENABLED", True):
        return DisabledCache()
    return FailOpenCache(
        InProcessCacheBackend(
            maxsize=int(getattr(settings, "READ_CACHE_MAX_ENTRIES", 2048)),
            default_ttl=int(getattr(settings, "REPORTING_CACHE_TTL_SECONDS", 30)),
        )
    )


def get_read_cache() -> CacheBackend:
    global _read_cache
    if _read_cache is None:
        _read_cache = build_read_cache()
    return _read_cache


def set_read_cache(backend: CacheBackend | None) -> None:
    """Test hook. Pass None to rebuild the default process cache on next get."""
    global _read_cache
    _read_cache = backend
