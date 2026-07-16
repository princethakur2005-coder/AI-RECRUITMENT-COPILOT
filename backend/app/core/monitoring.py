from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.services.cache import cache_service


class MetricsRegistry:
    """Provider-agnostic in-memory metrics abstraction with placeholder gauges and timings."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = defaultdict(float)
        self._timers: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0.0, "sum": 0.0, "max": 0.0})

    def _key(self, name: str, labels: dict[str, Any] | None = None) -> str:
        if not labels:
            return name
        labels_part = ",".join(f"{k}={labels[k]}" for k in sorted(labels))
        return f"{name}|{labels_part}"

    def increment(self, name: str, value: float = 1.0, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def set_gauge(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = value

    def observe(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            key = self._key(name, labels)
            record = self._timers[key]
            record["count"] += 1
            record["sum"] += value
            record["max"] = max(record["max"], value)

    def observe_http_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        if not settings.METRICS_ENABLED:
            return
        labels = {"method": method, "path": path, "status": status_code}
        self.increment("http_requests_total", labels=labels)
        self.observe("http_request_duration_ms", value=duration_ms, labels=labels)

    def observe_slow_request(self, method: str, path: str, duration_ms: float) -> None:
        if not settings.METRICS_ENABLED:
            return
        self.increment("http_slow_requests_total", labels={"method": method, "path": path})

    def observe_error(self, path: str, error_type: str) -> None:
        if not settings.METRICS_ENABLED:
            return
        self.increment("http_errors_total", labels={"path": path, "error_type": error_type})

    def update_resource_placeholders(self) -> None:
        if not settings.METRICS_ENABLED:
            return
        rss_mb = 0.0
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            rss_mb = (page_size * phys_pages) / (1024 * 1024)
        except Exception:
            rss_mb = 0.0

        self.set_gauge("resource_memory_placeholder_mb", rss_mb)
        self.set_gauge("resource_cpu_placeholder", 0.0)
        # Background worker placeholders
        self.set_gauge("background_worker_threads", float(settings.BACKGROUND_WORKER_THREADS))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timers": {k: dict(v) for k, v in self._timers.items()},
                "generated_at": time.time(),
            }


metrics_registry = MetricsRegistry()


def _check_database_health() -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def _check_redis_health() -> dict[str, Any]:
    if not settings.HEALTHCHECK_ENABLE_DEPENDENCIES:
        return {"status": "skipped"}

    try:
        health = cache_service.healthcheck()
        if health.get("backend_ok"):
            return {"status": "healthy", "backend": "redis"}
        if health.get("fallback_ok"):
            return {"status": "degraded", "backend": "fallback"}
        return {"status": "unhealthy", "backend": "redis"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def dependency_health_report() -> dict[str, Any]:
    db = _check_database_health()
    redis = _check_redis_health()

    statuses = [db.get("status"), redis.get("status")]
    if any(status == "unhealthy" for status in statuses):
        overall = "unhealthy"
    elif any(status == "degraded" for status in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "dependencies": {
            "database": db,
            "redis": redis,
        },
    }


def readiness_report(service_name: str) -> dict[str, Any]:
    metrics_registry.update_resource_placeholders()
    deps = dependency_health_report() if settings.HEALTHCHECK_ENABLE_DEPENDENCIES else {"status": "healthy", "dependencies": {}}

    return {
        "status": deps.get("status", "healthy"),
        "service": service_name,
        "dependencies": deps.get("dependencies", {}),
        "monitoring": {
            "enabled": settings.METRICS_ENABLED,
            "metrics": metrics_registry.snapshot(),
        },
    }


def liveness_report(service_name: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": service_name,
    }
