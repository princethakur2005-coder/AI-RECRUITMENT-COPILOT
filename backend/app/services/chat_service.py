from __future__ import annotations

from typing import Any, List, Dict, Optional

from app.services.ai_provider import GeminiProvider
from app.services.ai_config import get_ai_config
from app.services.cache import TTLCache, make_cache_key
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER


AI_RESPONSE_CACHE = TTLCache(maxsize=4096, ttl=1800)


class ChatService:
    """Simple reusable chat service that delegates to an AI provider.

    The service maintains an in-memory conversation history and formats messages
    using provider-agnostic prompt templates when available.
    """

    def __init__(self, provider: Optional[Any] = None, provider_name: str = "gemini") -> None:
        self.provider_name = provider_name
        self.config = get_ai_config(provider=provider_name)
        self.provider = provider or GeminiProvider(model=self.config.model)
        self.history: List[Dict[str, str]] = []

    def start_conversation(self, system_message: str | None = None) -> None:
        self.history = []
        if system_message:
            self.history.append({"role": "system", "content": system_message})

    def send_message(self, user_message: str) -> Dict[str, Any]:
        """Send a user message and receive AI response; history is kept."""
        self.history.append({"role": "user", "content": user_message})

        # Build a concatenated prompt from history
        prompt = self._build_prompt_from_history()

        cache_key = make_cache_key(
            self.provider_name,
            self.config.model,
            self.config.temperature,
            self.config.max_tokens,
            prompt,
        )
        cached = AI_RESPONSE_CACHE.get(cache_key)
        if cached is not None:
            self.history.append({"role": "assistant", "content": cached.get("content", "")})
            return cached

        resp = self.provider.generate(
            prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
        )
        AI_RESPONSE_CACHE.set(cache_key, resp)

        content = resp.get("content", "")
        self.history.append({"role": "assistant", "content": content})

        return {"content": content, "raw": resp}

    def _build_prompt_from_history(self) -> str:
        # format history to a single prompt string
        parts: List[str] = []
        for turn in self.history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            parts.append(f"[{role.upper()}] {content}")
        return "\n".join(parts)

    def ask_with_template(self, template_name: str, **kwargs: Any) -> Dict[str, Any]:
        tpl = DEFAULT_PROMPT_MANAGER.get_template(template_name)
        if tpl is None:
            raise KeyError(f"Unknown template: {template_name}")
        prompt = tpl.template.format_map({k: (v if v is not None else "") for k, v in kwargs.items()})
        return self.send_message(prompt)
