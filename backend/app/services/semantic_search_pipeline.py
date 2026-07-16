from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorRecord, VectorSearchResult, VectorStore


RESUME_NAMESPACE = "resume"
JOB_TEMPLATE_NAMESPACE = "job_template"


@dataclass
class SemanticDocument:
    id: str
    content: str
    metadata: Dict[str, Any]


class SemanticSearchPipeline:
    """Production-ready semantic indexing and retrieval pipeline.

    The pipeline remains provider-agnostic via:
    - `EmbeddingService` abstraction for embedding providers
    - `VectorStore` abstraction for vector database implementations
    """

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def index_resume(self, candidate_id: str, resume_text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        doc = SemanticDocument(id=f"resume:{candidate_id}", content=resume_text, metadata=metadata or {})
        self._index_documents(namespace=RESUME_NAMESPACE, source_id=candidate_id, documents=[doc])

    def index_job_template(
        self,
        template_id: str,
        role_title: str,
        template_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_content = f"{role_title}\n{template_text}".strip()
        merged_metadata = {"role_title": role_title, **(metadata or {})}
        doc = SemanticDocument(id=f"job:{template_id}", content=merged_content, metadata=merged_metadata)
        self._index_documents(namespace=JOB_TEMPLATE_NAMESPACE, source_id=template_id, documents=[doc])

    def bulk_index_resumes(self, items: List[Dict[str, Any]]) -> None:
        records: List[VectorRecord] = []
        payloads: List[tuple[str, SemanticDocument]] = []
        for item in items:
            candidate_id = str(item.get("candidate_id") or "").strip()
            resume_text = str(item.get("resume_text") or "")
            if not candidate_id or not resume_text:
                continue
            doc = SemanticDocument(
                id=f"resume:{candidate_id}",
                content=resume_text,
                metadata=dict(item.get("metadata") or {}),
            )
            payloads.append((candidate_id, doc))

        records = self._build_records(namespace=RESUME_NAMESPACE, source_and_docs=payloads)
        if records:
            self.vector_store.upsert(records)

    def bulk_index_job_templates(self, items: List[Dict[str, Any]]) -> None:
        payloads: List[tuple[str, SemanticDocument]] = []
        for item in items:
            template_id = str(item.get("template_id") or "").strip()
            role_title = str(item.get("role_title") or "").strip()
            template_text = str(item.get("template_text") or "")
            if not template_id or not template_text:
                continue
            content = f"{role_title}\n{template_text}".strip()
            metadata = {"role_title": role_title, **dict(item.get("metadata") or {})}
            doc = SemanticDocument(id=f"job:{template_id}", content=content, metadata=metadata)
            payloads.append((template_id, doc))

        records = self._build_records(namespace=JOB_TEMPLATE_NAMESPACE, source_and_docs=payloads)
        if records:
            self.vector_store.upsert(records)

    def semantic_search_resumes(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        return self._semantic_search(namespace=RESUME_NAMESPACE, query=query, top_k=top_k, filters=filters)

    def semantic_search_job_templates(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        return self._semantic_search(namespace=JOB_TEMPLATE_NAMESPACE, query=query, top_k=top_k, filters=filters)

    def _semantic_search(
        self,
        namespace: str,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[VectorSearchResult]:
        if not query.strip():
            return []
        query_embedding = self.embedding_service.embed_text(query)
        return self.vector_store.query(
            namespace=namespace,
            embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )

    def _index_documents(self, namespace: str, source_id: str, documents: List[SemanticDocument]) -> None:
        records = self._build_records(namespace=namespace, source_and_docs=[(source_id, doc) for doc in documents])
        if records:
            self.vector_store.upsert(records)

    def _build_records(self, namespace: str, source_and_docs: List[tuple[str, SemanticDocument]]) -> List[VectorRecord]:
        if not source_and_docs:
            return []

        texts = [doc.content for _, doc in source_and_docs]
        embeddings = self.embedding_service.embed_texts(texts)
        if len(embeddings) != len(source_and_docs):
            raise ValueError("Embedding generation returned mismatched item count")

        records: List[VectorRecord] = []
        for i, (source_id, doc) in enumerate(source_and_docs):
            records.append(
                VectorRecord(
                    id=doc.id,
                    namespace=namespace,
                    source_id=source_id,
                    content=doc.content,
                    embedding=embeddings[i],
                    metadata=doc.metadata,
                )
            )
        return records
