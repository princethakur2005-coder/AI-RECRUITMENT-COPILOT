from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional

import httpx


EmbeddingVector = List[float]


class EmbeddingProvider(ABC):
    """Provider contract for text embedding generation."""

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[EmbeddingVector]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embedding provider for baseline/offline usage.

    This is not model-quality semantic embedding but provides stable vectors
    for development, tests, and fallback operation.
    """

    def __init__(self, dimension: int = 256) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed_texts(self, texts: List[str]) -> List[EmbeddingVector]:
        vectors: List[EmbeddingVector] = []
        for text in texts:
            vectors.append(self._embed_one(text or ""))
        return vectors

    def _embed_one(self, text: str) -> EmbeddingVector:
        vector = [0.0] * self.dimension
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Use several digest bytes to spread token contribution.
            for i in range(0, min(len(digest), 16), 2):
                idx = digest[i] % self.dimension
                sign = 1.0 if digest[i + 1] % 2 == 0 else -1.0
                vector[idx] += sign

        return self._l2_normalize(vector)

    def _tokenize(self, text: str) -> List[str]:
        out: List[str] = []
        current = []
        for ch in text.lower():
            if ch.isalnum() or ch in {"#", "+", ".", "-", "_"}:
                current.append(ch)
            else:
                if current:
                    out.append("".join(current))
                    current = []
        if current:
            out.append("".join(current))
        return out

    def _l2_normalize(self, vector: EmbeddingVector) -> EmbeddingVector:
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]


class HTTPEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that calls an external embedding API endpoint.

    Expected response format:
      {"embeddings": [[...], [...]]}
    """

    def __init__(
        self,
        endpoint: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def embed_texts(self, texts: List[str]) -> List[EmbeddingVector]:
        payload: Dict[str, Any] = {"input": texts}
        if self.model:
            payload["model"] = self.model

        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(embeddings, list):
            raise ValueError("Embedding endpoint returned invalid payload")
        return [self._to_float_vector(item) for item in embeddings]

    def _to_float_vector(self, value: Any) -> EmbeddingVector:
        if not isinstance(value, list):
            raise ValueError("Embedding item must be a list")
        return [float(v) for v in value]


class EmbeddingService:
    """Reusable high-level service for embedding generation."""

    def __init__(self, provider: EmbeddingProvider, batch_size: int = 64) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.provider = provider
        self.batch_size = batch_size

    def embed_text(self, text: str) -> EmbeddingVector:
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else []

    def embed_texts(self, texts: List[str]) -> List[EmbeddingVector]:
        if not texts:
            return []

        all_vectors: List[EmbeddingVector] = []
        for batch in self._batched(texts, self.batch_size):
            vectors = self.provider.embed_texts(batch)
            if len(vectors) != len(batch):
                raise ValueError("Embedding provider returned mismatched vector count")
            all_vectors.extend(vectors)
        return all_vectors

    def _batched(self, items: List[str], batch_size: int) -> Iterable[List[str]]:
        for i in range(0, len(items), batch_size):
            yield items[i : i + batch_size]
