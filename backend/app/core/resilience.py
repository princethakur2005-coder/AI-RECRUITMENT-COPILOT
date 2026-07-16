from __future__ import annotations

import time
import logging
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable, Iterable, Type

logger = logging.getLogger("app.resilience")


class RetryPolicy:
    def __init__(self, attempts: int = 3, backoff_factor: float = 0.5, retry_exceptions: Iterable[Type[BaseException]] | None = None):
        self.attempts = max(1, attempts)
        self.backoff_factor = max(0.0, float(backoff_factor))
        self.retry_exceptions = tuple(retry_exceptions) if retry_exceptions else (Exception,)

    def __call__(self, func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, self.attempts + 1):
                try:
                    return func(*args, **kwargs)
                except self.retry_exceptions as exc:
                    last_exc = exc
                    wait = self.backoff_factor * (2 ** (attempt - 1))
                    logger.debug("RetryPolicy: attempt %s failed, sleeping %s seconds", attempt, wait)
                    time.sleep(wait)

            logger.exception("RetryPolicy: all attempts failed for %s", func)
            raise last_exc

        return wrapper


def run_with_timeout(func: Callable, timeout_seconds: int, *args, **kwargs):
    """Run a blocking callable with a timeout using a thread pool.

    Returns the function result or raises TimeoutError if timeout expires.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(func, *args, **kwargs)
        try:
            return fut.result(timeout=timeout_seconds)
        except FutureTimeout as exc:
            fut.cancel()
            raise TimeoutError("Operation timed out") from exc
