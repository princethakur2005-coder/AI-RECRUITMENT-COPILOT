from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any

from .gemini_client import GeminiClient


class AIProvider(ABC):
    """Generic interface for AI providers such as OpenAI, Ollama, or future backends."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def generate_structured(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Generate a response and coerce content into a JSON-compatible structure.

        This keeps higher-level services provider-agnostic for structured extraction.
        """
        response = self.generate(prompt, **kwargs)
        content = response.get("content")

        if isinstance(content, (dict, list)):
            return {"data": content, "raw": response, "status": "ok"}

        if isinstance(content, str):
            text = content.strip()
            if text.startswith("```"):
                lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
                text = "\n".join(lines).strip()
            try:
                parsed = json.loads(text)
                if isinstance(parsed, (dict, list)):
                    return {"data": parsed, "raw": response, "status": "ok"}
            except Exception:
                pass

        return {"data": {}, "raw": response, "status": "unstructured"}


class OpenAIProvider(AIProvider):
    """OpenAI-backed AI provider placeholder implementation."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "prompt": prompt,
            "content": "",
            "provider": "openai",
            "model": self.model,
            "status": "configured",
            "meta": kwargs,
        }


class GeminiProvider(AIProvider):
    """Provider implementation that delegates to the `GeminiClient`.

    The provider reads the Gemini API key from the environment if not supplied.
    Supported environment variables: `GEMINI_API_KEY`, `GOOGLE_GEMINI_API_KEY`.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.0", base_url: str | None = None) -> None:
        # Allow explicit key via kwargs or fall back to environment inside the client
        self.client = GeminiClient(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return self.client.generate_text(prompt, model=self.model, **kwargs)


class AIProviderFactory:
    """Factory for selecting AI providers in an extensible way."""

    @staticmethod
    def create(provider_name: str, **kwargs: Any) -> AIProvider:
        provider_name = (provider_name or "openai").lower()

        if provider_name == "openai":
            return OpenAIProvider(**kwargs)

        if provider_name == "gemini":
            return GeminiProvider(**kwargs)

        if provider_name == "ollama":
            return PlaceholderProvider("ollama", **kwargs)

        raise ValueError(f"Unsupported AI provider: {provider_name}")


class PlaceholderProvider(AIProvider):
    """Minimal placeholder for future providers such as Ollama."""

    def __init__(self, provider_name: str, **kwargs: Any) -> None:
        self.provider_name = provider_name
        self.kwargs = kwargs

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "prompt": prompt,
            "content": "",
            "provider": self.provider_name,
            "status": "configured",
            "meta": {**self.kwargs, **kwargs},
        }
