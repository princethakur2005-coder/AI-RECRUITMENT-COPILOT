from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.ai.config import AISettings, get_ai_settings
from app.ai.exceptions import AIConfigurationError
from app.ai.providers.base import AIProviderBase
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.openai_provider import OpenAIProvider


def create_ai_provider(settings: AISettings | None = None, **kwargs: Any) -> AIProviderBase:
    """Create an AI provider based on environment configuration."""
    resolved_settings = settings or get_ai_settings()
    provider_name = (resolved_settings.provider or "openai").lower()

    if provider_name == "openai":
        return OpenAIProvider(settings=resolved_settings)

    if provider_name == "gemini":
        return GeminiProvider(settings=resolved_settings)

    raise AIConfigurationError(f"Unsupported AI provider: {provider_name}")


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProviderBase:
    """Return a cached default provider instance for dependency injection."""
    return create_ai_provider()
