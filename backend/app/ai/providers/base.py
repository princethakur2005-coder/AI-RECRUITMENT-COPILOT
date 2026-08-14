from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(slots=True)
class AIGenerationResult:
    content: str
    provider: str
    model: str
    status: str
    latency_ms: float = 0.0
    token_usage: TokenUsage | None = None
    raw: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AIJSONResult:
    data: dict[str, Any] | list[Any]
    provider: str
    model: str
    status: str
    latency_ms: float = 0.0
    token_usage: TokenUsage | None = None
    raw: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingResult:
    """Placeholder embedding response for future vector workflows."""

    status: str
    provider: str
    model: str
    vector: list[float] = field(default_factory=list)
    dimensions: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class AIProviderBase(ABC):
    """Abstract interface implemented by every AI provider."""

    provider_name: str

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> AIGenerationResult:
        """Generate plain-text content from a prompt."""

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> AIJSONResult:
        """Generate structured JSON content from a prompt."""

    def embedding(
        self,
        text: str,
        *,
        model: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        """Placeholder for future embedding support."""
        return EmbeddingResult(
            status="not_implemented",
            provider=self.provider_name,
            model=model or "embedding-placeholder",
            vector=[],
            dimensions=0,
            meta={"message": "Embeddings are not enabled in the AI foundation layer yet."},
        )
