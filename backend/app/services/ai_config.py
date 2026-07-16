from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Dict, Optional


@dataclass
class AIConfig:
    provider: Optional[str]
    model: str
    temperature: float
    max_tokens: int
    timeout: int
    raw: Dict[str, Any]

    @classmethod
    def from_env(cls, provider: Optional[str] = None) -> "AIConfig":
        """Build an AIConfig by reading environment variables.

        Resolution order for a setting (example for MODEL):
        1. Provider-specific: e.g. `GEMINI_MODEL`
        2. Generic AI override: `AI_MODEL`
        3. Plain legacy: `MODEL`
        4. Fallback default provided here
        """

        provider_key = provider.upper() if provider else None

        def _get(key: str, default: Any) -> Any:
            # provider-specific
            if provider_key:
                val = os.environ.get(f"{provider_key}_{key}")
                if val is not None:
                    return val

            # generic AI override
            val = os.environ.get(f"AI_{key}")
            if val is not None:
                return val

            # legacy/plain
            val = os.environ.get(key)
            if val is not None:
                return val

            return default

        model = str(_get("MODEL", "gpt-4o-mini"))
        try:
            temperature = float(_get("TEMPERATURE", 0.7))
        except (TypeError, ValueError):
            temperature = 0.7

        try:
            max_tokens = int(_get("MAX_TOKENS", 1024))
        except (TypeError, ValueError):
            max_tokens = 1024

        try:
            timeout = int(_get("TIMEOUT", 30))
        except (TypeError, ValueError):
            timeout = 30

        raw = {
            "provider_specific": {f"{provider_key}_{k}": os.environ.get(f"{provider_key}_{k}") for k in ("MODEL", "TEMPERATURE", "MAX_TOKENS", "TIMEOUT")} if provider_key else {},
            "ai_overrides": {f"AI_{k}": os.environ.get(f"AI_{k}") for k in ("MODEL", "TEMPERATURE", "MAX_TOKENS", "TIMEOUT")},
            "legacy": {k: os.environ.get(k) for k in ("MODEL", "TEMPERATURE", "MAX_TOKENS", "TIMEOUT")},
        }

        return cls(
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            raw=raw,
        )


def get_ai_config(provider: Optional[str] = None) -> AIConfig:
    """Convenience factory to obtain an `AIConfig` for a provider (or generic)."""

    return AIConfig.from_env(provider)
