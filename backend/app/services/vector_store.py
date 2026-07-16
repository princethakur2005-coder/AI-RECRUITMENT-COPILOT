from __future__ import annotations

import json
import math
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


Vector = List[float]


@dataclass
class VectorRecord:
    id: str
    namespace: str
    source_id: str
    embedding: Vector
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class VectorSearchResult:
    id: str
    source_id: str
    namespace: str
    score: float
    content: Optional[str]
    metadata: Dict[str, Any]


class VectorStore(ABC):
    """Provider-agnostic vector storage contract."""

    @abstractmethod
    def upsert(self, records: List[VectorRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        namespace: str,
        embedding: Vector,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """Thread-safe in-memory vector store for local/dev usage."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, VectorRecord] = {}

    def upsert(self, records: List[VectorRecord]) -> None:
        with self._lock:
            for record in records:
                self._records[record.id] = record

    def query(
        self,
        namespace: str,
        embedding: Vector,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        with self._lock:
            candidates: List[VectorSearchResult] = []
            for record in self._records.values():
                if record.namespace != namespace:
                    continue
                if not self._match_filters(record.metadata or {}, filters):
                    continue
                score = self._cosine_similarity(embedding, record.embedding)
                candidates.append(
                    VectorSearchResult(
                        id=record.id,
                        source_id=record.source_id,
                        namespace=record.namespace,
                        score=score,
                        content=record.content,
                        metadata=record.metadata or {},
                    )
                )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: max(1, top_k)]

    def _match_filters(self, metadata: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if metadata.get(key) != value:
                return False
        return True

    def _cosine_similarity(self, a: Vector, b: Vector) -> float:
        if not a or not b:
            return 0.0
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(dot / (norm_a * norm_b))


class PgVectorStore(VectorStore):
    """PostgreSQL-backed vector store.

    Supports two execution modes:
    - `use_pgvector=True`: uses pgvector extension and `<=>` distance operator.
    - `use_pgvector=False`: stores embeddings as JSONB and scores in application code.

    This keeps architecture decoupled from a single vector backend while allowing
    production pgvector acceleration when available.
    """

    def __init__(
        self,
        db: Session,
        table_name: str = "semantic_embeddings",
        embedding_dim: int = 256,
        use_pgvector: bool = True,
    ) -> None:
        self.db = db
        self.table_name = table_name
        self.embedding_dim = embedding_dim
        self.use_pgvector = use_pgvector

    def ensure_schema(self) -> None:
        if self.use_pgvector:
            self.db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    content TEXT NULL,
                    embedding_json JSONB NOT NULL,
                    embedding VECTOR({self.embedding_dim}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """
        else:
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    content TEXT NULL,
                    embedding_json JSONB NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """

        self.db.execute(text(create_sql))
        self.db.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_namespace ON {self.table_name}(namespace)"))
        if self.use_pgvector:
            self.db.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_embedding ON {self.table_name} "
                    f"USING ivfflat (embedding vector_cosine_ops)"
                )
            )
        self.db.commit()

    def upsert(self, records: List[VectorRecord]) -> None:
        if not records:
            return

        now = datetime.now(timezone.utc).isoformat()
        for record in records:
            embedding_json = json.dumps(record.embedding)
            metadata_json = json.dumps(record.metadata or {})

            if self.use_pgvector:
                query = text(
                    f"""
                    INSERT INTO {self.table_name}
                        (id, namespace, source_id, content, embedding_json, embedding, metadata, created_at, updated_at)
                    VALUES
                        (:id, :namespace, :source_id, :content, CAST(:embedding_json AS JSONB), :embedding_literal::vector, CAST(:metadata AS JSONB), :created_at, :updated_at)
                    ON CONFLICT (id) DO UPDATE SET
                        namespace = EXCLUDED.namespace,
                        source_id = EXCLUDED.source_id,
                        content = EXCLUDED.content,
                        embedding_json = EXCLUDED.embedding_json,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """
                )
                self.db.execute(
                    query,
                    {
                        "id": record.id,
                        "namespace": record.namespace,
                        "source_id": record.source_id,
                        "content": record.content,
                        "embedding_json": embedding_json,
                        "embedding_literal": self._to_pgvector_literal(record.embedding),
                        "metadata": metadata_json,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            else:
                query = text(
                    f"""
                    INSERT INTO {self.table_name}
                        (id, namespace, source_id, content, embedding_json, metadata, created_at, updated_at)
                    VALUES
                        (:id, :namespace, :source_id, :content, CAST(:embedding_json AS JSONB), CAST(:metadata AS JSONB), :created_at, :updated_at)
                    ON CONFLICT (id) DO UPDATE SET
                        namespace = EXCLUDED.namespace,
                        source_id = EXCLUDED.source_id,
                        content = EXCLUDED.content,
                        embedding_json = EXCLUDED.embedding_json,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """
                )
                self.db.execute(
                    query,
                    {
                        "id": record.id,
                        "namespace": record.namespace,
                        "source_id": record.source_id,
                        "content": record.content,
                        "embedding_json": embedding_json,
                        "metadata": metadata_json,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

        self.db.commit()

    def query(
        self,
        namespace: str,
        embedding: Vector,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        limit = max(1, top_k)

        if self.use_pgvector:
            sql = f"""
                SELECT id, source_id, namespace, content, metadata, (1 - (embedding <=> :query_embedding::vector)) AS score
                FROM {self.table_name}
                WHERE namespace = :namespace
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :limit
            """
            rows = self.db.execute(
                text(sql),
                {
                    "namespace": namespace,
                    "query_embedding": self._to_pgvector_literal(embedding),
                    "limit": limit,
                },
            ).mappings()
            results = [self._map_row(row) for row in rows]
            return self._filter_results(results, filters)

        rows = self.db.execute(
            text(
                f"""
                SELECT id, source_id, namespace, content, metadata, embedding_json
                FROM {self.table_name}
                WHERE namespace = :namespace
                """
            ),
            {"namespace": namespace},
        ).mappings()

        scored: List[VectorSearchResult] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if not self._match_filters(metadata, filters):
                continue
            raw_embedding = row.get("embedding_json")
            if isinstance(raw_embedding, str):
                raw_embedding = json.loads(raw_embedding)
            score = self._cosine_similarity(embedding, [float(v) for v in (raw_embedding or [])])
            scored.append(
                VectorSearchResult(
                    id=str(row.get("id")),
                    source_id=str(row.get("source_id")),
                    namespace=str(row.get("namespace")),
                    score=score,
                    content=row.get("content"),
                    metadata=metadata,
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def _map_row(self, row: Any) -> VectorSearchResult:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return VectorSearchResult(
            id=str(row.get("id")),
            source_id=str(row.get("source_id")),
            namespace=str(row.get("namespace")),
            score=float(row.get("score") or 0.0),
            content=row.get("content"),
            metadata=metadata,
        )

    def _to_pgvector_literal(self, vector: Vector) -> str:
        return "[" + ",".join(str(float(v)) for v in vector) + "]"

    def _filter_results(self, items: List[VectorSearchResult], filters: Optional[Dict[str, Any]]) -> List[VectorSearchResult]:
        if not filters:
            return items
        out: List[VectorSearchResult] = []
        for item in items:
            if self._match_filters(item.metadata, filters):
                out.append(item)
        return out

    def _match_filters(self, metadata: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if metadata.get(key) != value:
                return False
        return True

    def _cosine_similarity(self, a: Vector, b: Vector) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(dot / (norm_a * norm_b))
