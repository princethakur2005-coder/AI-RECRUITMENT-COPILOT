from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai.config import AISettings, get_ai_settings
from app.ai.exceptions import AIProviderError
from app.ai.providers.base import AIJSONResult, AIGenerationResult, AIProviderBase, TokenUsage
from app.ai.utils.json_validation import parse_json_content
from app.ai.utils.logging import log_ai_request


class OpenAIProvider(AIProviderBase):
    """OpenAI chat-completions provider."""

    provider_name = "openai"

    def __init__(self, settings: AISettings | None = None) -> None:
        self.settings = settings or get_ai_settings()
        self.api_key = self.settings.OPENAI_API_KEY
        self.base_url = self.settings.OPENAI_BASE_URL.rstrip("/")

    def _request(
        self,
        prompt: str,
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        timeout: int | None,
        response_format: dict[str, str] | None = None,
    ) -> AIGenerationResult:
        resolved_model = model or self.settings.model
        resolved_temperature = temperature if temperature is not None else self.settings.temperature
        resolved_max_tokens = max_tokens or self.settings.max_tokens
        resolved_timeout = timeout or self.settings.timeout

        if not self.api_key:
            result = AIGenerationResult(
                content="",
                provider=self.provider_name,
                model=resolved_model,
                status="no_api_key",
                meta={"error": "OPENAI_API_KEY is not configured"},
            )
            log_ai_request(
                provider=result.provider,
                model=result.model,
                latency_ms=0.0,
                token_usage=None,
                success=False,
                error="OPENAI_API_KEY is not configured",
            )
            return result

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": resolved_temperature,
            "max_tokens": resolved_max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=resolved_timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            log_ai_request(
                provider=self.provider_name,
                model=resolved_model,
                latency_ms=latency_ms,
                token_usage=None,
                success=False,
                error=str(exc),
            )
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        content = ""
        token_usage = None
        if isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                content = str(message.get("content", ""))
            usage = data.get("usage")
            if isinstance(usage, dict):
                token_usage = TokenUsage(
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )

        result = AIGenerationResult(
            content=content,
            provider=self.provider_name,
            model=resolved_model,
            status="ok",
            latency_ms=latency_ms,
            token_usage=token_usage,
            raw=data if isinstance(data, dict) else None,
        )
        log_ai_request(
            provider=result.provider,
            model=result.model,
            latency_ms=latency_ms,
            token_usage=token_usage,
            success=True,
        )
        return result

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
        return self._request(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

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
        generation = self._request(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            response_format={"type": "json_object"},
        )
        parsed = parse_json_content(generation.content)
        return AIJSONResult(
            data=parsed,
            provider=generation.provider,
            model=generation.model,
            status=generation.status,
            latency_ms=generation.latency_ms,
            token_usage=generation.token_usage,
            raw=generation.raw,
            meta=generation.meta,
        )
