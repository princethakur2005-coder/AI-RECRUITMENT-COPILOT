from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AI_PROVIDER_CHOICES = ("openai", "gemini")

BASE_DIR = Path(__file__).resolve().parents[2]


class AISettings(BaseSettings):
    """Centralized AI configuration loaded from environment variables."""

    AI_PROVIDER: Literal["openai", "gemini"] = Field(default="openai", env="AI_PROVIDER")
    AI_MODEL: str = Field(default="gpt-4o-mini", env="AI_MODEL")
    AI_TEMPERATURE: float = Field(default=0.2, env="AI_TEMPERATURE")
    AI_MAX_TOKENS: int = Field(default=1024, env="AI_MAX_TOKENS")
    AI_TIMEOUT: int = Field(default=30, env="AI_TIMEOUT")
    AI_RETRY_ATTEMPTS: int = Field(default=3, env="AI_RETRY_ATTEMPTS")
    AI_RETRY_BACKOFF_FACTOR: float = Field(default=0.5, env="AI_RETRY_BACKOFF_FACTOR")

    OPENAI_API_KEY: str | None = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")

    GEMINI_API_KEY: str | None = Field(default=None, env="GEMINI_API_KEY")
    GOOGLE_GEMINI_API_KEY: str | None = Field(default=None, env="GOOGLE_GEMINI_API_KEY")
    GEMINI_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        env="GEMINI_BASE_URL",
    )

    @field_validator("AI_TEMPERATURE")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("AI_TEMPERATURE must be between 0.0 and 2.0")
        return value

    @field_validator("AI_MAX_TOKENS")
    @classmethod
    def validate_max_tokens(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AI_MAX_TOKENS must be at least 1")
        return value

    @field_validator("AI_TIMEOUT")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AI_TIMEOUT must be at least 1 second")
        return value

    @property
    def provider(self) -> str:
        return self.AI_PROVIDER

    @property
    def model(self) -> str:
        return self._provider_override("MODEL", self.AI_MODEL)

    @property
    def temperature(self) -> float:
        override = self._provider_override("TEMPERATURE", None)
        if override is not None:
            try:
                return float(override)
            except (TypeError, ValueError):
                pass
        return self.AI_TEMPERATURE

    @property
    def max_tokens(self) -> int:
        override = self._provider_override("MAX_TOKENS", None)
        if override is not None:
            try:
                return int(override)
            except (TypeError, ValueError):
                pass
        return self.AI_MAX_TOKENS

    @property
    def timeout(self) -> int:
        override = self._provider_override("TIMEOUT", None)
        if override is not None:
            try:
                return int(override)
            except (TypeError, ValueError):
                pass
        return self.AI_TIMEOUT

    @property
    def gemini_api_key(self) -> str | None:
        return self.GEMINI_API_KEY or self.GOOGLE_GEMINI_API_KEY

    def _provider_override(self, key: str, default: str | None) -> str | None:
        provider_key = f"{self.AI_PROVIDER.upper()}_{key}"
        import os

        value = os.environ.get(provider_key)
        if value is not None:
            return value
        return default

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache(maxsize=1)
def get_ai_settings() -> AISettings:
    """Return cached AI settings for dependency injection."""
    return AISettings()
