from __future__ import annotations

import logging

from app.ai.providers.base import TokenUsage

logger = logging.getLogger("app.ai")


def log_ai_request(
    *,
    provider: str,
    model: str,
    latency_ms: float,
    token_usage: TokenUsage | None,
    success: bool,
    pipeline: str | None = None,
    error: str | None = None,
) -> None:
    """Centralized AI request logging hook."""
    payload = {
        "event": "ai_request",
        "provider": provider,
        "model": model,
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "pipeline": pipeline,
        "token_usage": token_usage.to_dict() if token_usage else None,
        "error": error,
    }

    if success:
        logger.info("AI request completed", extra=payload)
    else:
        logger.warning("AI request failed", extra=payload)
