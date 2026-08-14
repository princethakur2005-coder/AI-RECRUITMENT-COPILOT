from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai.config import AISettings, get_ai_settings
from app.ai.exceptions import AIProviderError
from app.ai.providers.base import AIJSONResult, AIGenerationResult, AIProviderBase, TokenUsage
from app.ai.utils.json_validation import parse_json_content
from app.ai.utils.logging import log_ai_request


class GeminiProvider(AIProviderBase):
    """Google Gemini generateContent provider."""

    provider_name = "gemini"

    def __init__(self, settings: AISettings | None = None) -> None:
        self.settings = settings or get_ai_settings()
        self.api_key = self.settings.gemini_api_key
        self.base_url = self.settings.GEMINI_BASE_URL.rstrip("/")

    def _extract_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return ""

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            return ""

        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
        return "\n".join(texts).strip()

    def _request(
        self,
        prompt: str,
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        timeout: int | None,
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
                meta={"error": "GEMINI_API_KEY is not configured"},
            )
            log_ai_request(
                provider=result.provider,
                model=result.model,
                latency_ms=0.0,
                token_usage=None,
                success=False,
                error="GEMINI_API_KEY is not configured",
            )
            return result

        url = f"{self.base_url}/models/{resolved_model}:generateContent"
        params = {"key": self.api_key}
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": resolved_temperature,
                "maxOutputTokens": resolved_max_tokens,
            },
        }

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=resolved_timeout) as client:
                response = client.post(url, params=params, json=payload)
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
            raise AIProviderError(f"Gemini request failed: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        content = self._extract_text(data) if isinstance(data, dict) else ""
        token_usage = None
        if isinstance(data, dict):
            usage = data.get("usageMetadata")
            if isinstance(usage, dict):
                token_usage = TokenUsage(
                    prompt_tokens=usage.get("promptTokenCount"),
                    completion_tokens=usage.get("candidatesTokenCount"),
                    total_tokens=usage.get("totalTokenCount"),
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
        json_prompt = (
            f"{prompt}\n\nRespond with valid JSON only. Do not include markdown fences or commentary."
        )
        generation = self._request(
            json_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
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
