from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from copy import deepcopy
from functools import wraps
from typing import Any, Protocol

from app.core.config import settings

try:
    from redis import Redis
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - optional dependency fallback
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass


def _serialize_value(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        return str(value)


def make_cache_key(*args: Any, **kwargs: Any) -> str:
    payload = []
    for arg in args:
        payload.append(_serialize_value(arg))
    for key in sorted(kwargs):
        payload.append(f"{key}={_serialize_value(kwargs[key])}")
    raw = "|".join(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def memoize(ttl: int = 600, maxsize: int = 1024):
    cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_args = args
            if args and hasattr(args[0], "__class__") and fn.__qualname__.startswith(f"{args[0].__class__.__name__}."):
                cache_args = args[1:]
            key = make_cache_key(fn.__module__, fn.__qualname__, cache_args, kwargs)
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache
        return wrapper



class TTLCache:
    """Simple thread-safe in-memory TTL cache with max size control."""

    def __init__(self, maxsize: int = 1024, ttl: int = 600) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = time.time()
        keys_to_delete = [key for key, (expires, _) in self._store.items() if expires <= now]
        for key in keys_to_delete:
            self._store.pop(key, None)
        if len(self._store) > self.maxsize:
            # Drop oldest entries if cache grows too large
            sorted_items = sorted(self._store.items(), key=lambda item: item[1][0])
            for key, _ in sorted_items[: len(self._store) - self.maxsize]:
                self._store.pop(key, None)

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires, value = entry
            if expires <= time.time():
                self._store.pop(key, None)
                return None
            return deepcopy(value)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._prune()
            if len(self._store) >= self.maxsize:
                self._prune()
            expiry = time.time() + (ttl if ttl is not None else self.ttl)
            self._store[key] = (expiry, deepcopy(value))

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def keys(self, prefix: str) -> list[str]:
        with self._lock:
            self._prune()
            return [key for key in self._store if key.startswith(prefix)]

    def ping(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None:
        ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ...

    def delete(self, key: str) -> bool:
        ...

    def keys(self, prefix: str) -> list[str]:
        ...

    def clear(self) -> None:
        ...

    def ping(self) -> bool:
        ...


class RedisCacheBackend:
    """Redis-backed cache backend with JSON payload serialization."""

    def __init__(
        self,
        redis_url: str,
        default_ttl: int,
        prefix: str,
        connect_timeout: int,
        socket_timeout: int,
        healthcheck_timeout: int,
    ) -> None:
        self._default_ttl = default_ttl
        self._prefix = prefix.strip()
        self._healthcheck_timeout = healthcheck_timeout
        self._client: Redis | None = None

        if Redis is not None:
            self._client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=connect_timeout,
                socket_timeout=socket_timeout,
                health_check_interval=healthcheck_timeout,
                retry_on_timeout=True,
            )

    def _k(self, key: str) -> str:
        if not self._prefix:
            return key
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._k(key))
            if raw is None:
                return None
            return json.loads(raw)
        except (RedisError, ValueError, TypeError):
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._client is None:
            return
        try:
            payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
            self._client.set(self._k(key), payload, ex=max(1, ttl if ttl is not None else self._default_ttl))
        except RedisError:
            return

    def delete(self, key: str) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.delete(self._k(key)))
        except RedisError:
            return False

    def keys(self, prefix: str) -> list[str]:
        if self._client is None:
            return []
        try:
            scoped = self._k(prefix)
            values = self._client.keys(f"{scoped}*")
            if not self._prefix:
                return values
            strip_len = len(f"{self._prefix}:")
            return [key[strip_len:] if key.startswith(f"{self._prefix}:") else key for key in values]
        except RedisError:
            return []

    def clear(self) -> None:
        if self._client is None:
            return
        try:
            if not self._prefix:
                self._client.flushdb()
                return
            values = self._client.keys(f"{self._prefix}:*")
            if values:
                self._client.delete(*values)
        except RedisError:
            return

    def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.ping())
        except RedisError:
            return False

    @property
    def client(self) -> Redis | None:
        return self._client


class CacheService:
    """Provider-agnostic cache abstraction with Redis-primary/local fallback behavior."""

    def __init__(
        self,
        backend: CacheBackend,
        fallback: TTLCache | None = None,
        default_ttl: int = 600,
    ) -> None:
        self._backend = backend
        self._fallback = fallback or TTLCache(maxsize=settings.CACHE_MAX_LOCAL_ENTRIES, ttl=default_ttl)
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        value = self._backend.get(key)
        if value is not None:
            return value
        return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        resolved_ttl = ttl if ttl is not None else self.default_ttl
        self._backend.set(key, value, ttl=resolved_ttl)
        self._fallback.set(key, value, ttl=resolved_ttl)

    def delete(self, key: str) -> bool:
        backend_deleted = self._backend.delete(key)
        fallback_deleted = self._fallback.delete(key)
        return backend_deleted or fallback_deleted

    def invalidate(self, key: str) -> bool:
        return self.delete(key)

    def invalidate_prefix(self, prefix: str) -> int:
        keys = self._backend.keys(prefix)
        deleted = 0
        for key in keys:
            if self._backend.delete(key):
                deleted += 1
        for key in self._fallback.keys(prefix):
            if self._fallback.delete(key):
                deleted += 1
        return deleted

    def healthcheck(self) -> dict[str, Any]:
        backend_ok = self._backend.ping()
        fallback_ok = self._fallback.ping()
        return {
            "backend_ok": backend_ok,
            "fallback_ok": fallback_ok,
            "healthy": backend_ok or fallback_ok,
        }

    def clear(self) -> None:
        self._backend.clear()
        self._fallback.clear()

    def cache_control_header(self, ttl: int | None = None) -> dict[str, str]:
        resolved = ttl if ttl is not None else self.default_ttl
        return {"Cache-Control": f"public, max-age={int(resolved)}"}


class CacheInvalidationService:
    """Cache invalidation abstraction with namespaced invalidation placeholders."""

    def __init__(self, cache: CacheService, namespace: str = settings.CACHE_INVALIDATION_PREFIX) -> None:
        self._cache = cache
        self._namespace = namespace

    def invalidate_entity(self, entity_type: str, entity_id: str) -> int:
        prefix = f"{self._namespace}:{entity_type}:{entity_id}"
        return self._cache.invalidate_prefix(prefix)

    def invalidate_group(self, group_name: str) -> int:
        prefix = f"{self._namespace}:{group_name}"
        return self._cache.invalidate_prefix(prefix)


class BackgroundJobQueuePlaceholder:
    """Queue placeholder abstraction for future worker execution integrations."""

    def __init__(self, cache: CacheService, queue_prefix: str = settings.JOB_QUEUE_PREFIX) -> None:
        self._cache = cache
        self._queue_prefix = queue_prefix

    def queue_key(self, queue_name: str = "default") -> str:
        return f"{self._queue_prefix}:{queue_name}"

    def enqueue(self, payload: dict[str, Any], queue_name: str = "default", ttl: int | None = None) -> str:
        item_id = make_cache_key(queue_name, payload, time.time())
        key = f"{self.queue_key(queue_name)}:{item_id}"
        self._cache.set(key, payload, ttl=ttl or settings.CACHE_DEFAULT_TTL_SECONDS)
        return item_id

    def acknowledge(self, queue_name: str, item_id: str) -> bool:
        return self._cache.delete(f"{self.queue_key(queue_name)}:{item_id}")


class DistributedLockPlaceholder:
    """Distributed lock placeholder abstraction for provider-agnostic lock orchestration."""

    def __init__(self, cache: CacheService, lock_prefix: str = settings.DISTRIBUTED_LOCK_PREFIX) -> None:
        self._cache = cache
        self._lock_prefix = lock_prefix

    def _key(self, name: str) -> str:
        return f"{self._lock_prefix}:{name}"

    def acquire(self, name: str, owner: str, ttl_seconds: int = 30) -> bool:
        key = self._key(name)
        existing = self._cache.get(key)
        if existing is not None:
            return False
        self._cache.set(key, {"owner": owner, "acquired_at": time.time()}, ttl=ttl_seconds)
        return True

    def release(self, name: str, owner: str | None = None) -> bool:
        key = self._key(name)
        existing = self._cache.get(key)
        if existing is None:
            return False
        if owner is not None and isinstance(existing, dict) and existing.get("owner") != owner:
            return False
        return self._cache.delete(key)


class SessionCachePlaceholder:
    """Session cache placeholder abstraction for user/session scoped cache payloads."""

    def __init__(self, cache: CacheService, prefix: str = settings.SESSION_CACHE_PREFIX) -> None:
        self._cache = cache
        self._prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}"

    def set_session(self, session_id: str, data: dict[str, Any], ttl_seconds: int | None = None) -> None:
        self._cache.set(self._key(session_id), data, ttl=ttl_seconds or settings.CACHE_DEFAULT_TTL_SECONDS)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        value = self._cache.get(self._key(session_id))
        return value if isinstance(value, dict) else None

    def invalidate_session(self, session_id: str) -> bool:
        return self._cache.delete(self._key(session_id))


def _build_cache_service() -> CacheService:
    local = TTLCache(maxsize=settings.CACHE_MAX_LOCAL_ENTRIES, ttl=settings.CACHE_DEFAULT_TTL_SECONDS)

    if settings.REDIS_ENABLED:
        redis_backend = RedisCacheBackend(
            redis_url=settings.REDIS_URL,
            default_ttl=settings.CACHE_DEFAULT_TTL_SECONDS,
            prefix=settings.REDIS_PREFIX,
            connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            healthcheck_timeout=settings.REDIS_HEALTHCHECK_TIMEOUT_SECONDS,
        )
        return CacheService(backend=redis_backend, fallback=local, default_ttl=settings.CACHE_DEFAULT_TTL_SECONDS)

    return CacheService(backend=local, fallback=local, default_ttl=settings.CACHE_DEFAULT_TTL_SECONDS)


cache_service = _build_cache_service()
cache_invalidation_service = CacheInvalidationService(cache=cache_service)
background_job_queue = BackgroundJobQueuePlaceholder(cache=cache_service)
distributed_lock_service = DistributedLockPlaceholder(cache=cache_service)
session_cache_service = SessionCachePlaceholder(cache=cache_service)


def memoize(ttl: int = 600, maxsize: int = 1024):
    cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_args = args
            if args and hasattr(args[0], "__class__") and fn.__qualname__.startswith(f"{args[0].__class__.__name__}."):
                cache_args = args[1:]
            key = make_cache_key(fn.__module__, fn.__qualname__, cache_args, kwargs)
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache
        return wrapper


def paginate_params(page: int | None = None, page_size: int | None = None, *, max_page_size: int = 100) -> dict[str, int]:
    """Return offset/limit pagination parameters with safe bounds.

    This is a lightweight helper; integrate with ORM query builders where appropriate.
    """
    if page is None or page < 1:
        page = 1
    if page_size is None or page_size < 1:
        page_size = 25
    page_size = min(page_size, max_page_size)
    offset = (page - 1) * page_size
    return {"limit": page_size, "offset": offset}


def db_pool_config_placeholder() -> dict[str, int]:
    """Return connection pool configuration derived from settings (placeholder).

    Integrate these values with SQLAlchemy Engine creation or database driver configuration.
    """
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
    }

