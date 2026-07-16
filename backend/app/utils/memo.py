from __future__ import annotations

from functools import lru_cache, wraps
from typing import Any, Callable


def memoize(ttl: int = 600, maxsize: int = 1024):
    """A lightweight fallback memoize decorator using lru_cache.

    This is intentionally simple and does not implement TTL semantics.
    It provides safe import-time behavior without depending on cache backends.
    """

    def decorator(fn: Callable[..., Any]):
        cached = lru_cache(maxsize=maxsize)(fn)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return cached(*args, **kwargs)

        wrapper.cache = cached
        return wrapper

    return decorator
