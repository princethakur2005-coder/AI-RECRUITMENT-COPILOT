from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Optional, Protocol
import json
import os
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


@dataclass
class PromptEntry:
    id: str
    key: str
    category: str
    purpose: str
    version: int
    system_prompt: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class PromptResolution:
    key: str
    category: str
    purpose: str
    version: int
    prompt: str
    prompt_id: str
    metadata: Dict[str, Any]


@dataclass
class KnowledgeAsset:
    id: str
    asset_key: str
    category: str
    purpose: str
    content: str
    source_uri: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass
class RagQueryRequest:
    query: str
    top_k: int = 5
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RagContextChunk:
    asset_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnowledgeRetriever(Protocol):
    """Provider-agnostic retrieval interface for future RAG connectors."""

    def retrieve(self, request: RagQueryRequest) -> List[RagContextChunk]:
        ...


class InMemoryKnowledgeRetriever:
    """Fallback retriever for environments without vector search infra.

    Uses deterministic lexical overlap for baseline retrieval.
    """

    def __init__(self, registry: AIKnowledgePromptRegistry) -> None:  # type: ignore[name-defined]
        self.registry = registry

    def retrieve(self, request: RagQueryRequest) -> List[RagContextChunk]:
        tokens = set(self._tokenize(request.query))
        if not tokens:
            return []

        chunks: List[RagContextChunk] = []
        for asset in self.registry.list_knowledge_assets(active_only=True):
            if request.filters and not self._match_filters(asset.metadata, request.filters):
                continue
            asset_tokens = set(self._tokenize(asset.content))
            if not asset_tokens:
                continue
            overlap = len(tokens & asset_tokens)
            if overlap == 0:
                continue
            score = overlap / max(1, len(tokens))
            chunks.append(
                RagContextChunk(
                    asset_id=asset.id,
                    content=asset.content,
                    score=round(score, 4),
                    metadata={
                        "asset_key": asset.asset_key,
                        "category": asset.category,
                        "purpose": asset.purpose,
                        **asset.metadata,
                    },
                )
            )

        chunks.sort(key=lambda item: item.score, reverse=True)
        return chunks[: max(1, request.top_k)]

    def _tokenize(self, text: str) -> List[str]:
        out: List[str] = []
        current = []
        for ch in (text or "").lower():
            if ch.isalnum() or ch in {"_", "-", "+", "#", "."}:
                current.append(ch)
            else:
                if current:
                    out.append("".join(current))
                    current = []
        if current:
            out.append("".join(current))
        return out

    def _match_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, value in filters.items():
            if metadata.get(key) != value:
                return False
        return True


class AIKnowledgePromptRegistry:
    """Centralized registry for reusable prompts and AI knowledge assets.

    Enterprise design goals:
    - Prompt versioning and lifecycle management
    - Organization by category/purpose for governance and discoverability
    - Provider-agnostic retrieval contract for future RAG integration
    - Single reusable API for future AI modules to avoid code duplication
    """

    STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai_knowledge_prompt_registry.json")

    def __init__(self, retriever: Optional[KnowledgeRetriever] = None) -> None:
        self._lock = RLock()
        self._prompts: Dict[str, List[PromptEntry]] = {}
        self._knowledge_assets: Dict[str, KnowledgeAsset] = {}
        self._ensure_storage()
        self._load()
        self._load_defaults()
        self.retriever: KnowledgeRetriever = retriever or InMemoryKnowledgeRetriever(self)

    # ---------------------------
    # Prompt APIs
    # ---------------------------
    def register_prompt(
        self,
        key: str,
        category: str,
        purpose: str,
        system_prompt: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptEntry:
        """Creates version 1 when key is new, otherwise appends next version."""
        with self._lock:
            versions = self._prompts.get(key, [])
            next_version = 1 if not versions else max(item.version for item in versions) + 1
            entry = PromptEntry(
                id=str(uuid.uuid4()),
                key=key,
                category=category.strip().lower(),
                purpose=purpose.strip().lower(),
                version=next_version,
                system_prompt=system_prompt,
                description=description,
                tags=[tag.strip().lower() for tag in (tags or []) if tag and tag.strip()],
                active=active,
                metadata=metadata or {},
            )
            versions.append(entry)
            self._prompts[key] = versions
            self._persist()
            return entry

    def add_prompt_version(
        self,
        key: str,
        system_prompt: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptEntry:
        base = self.get_prompt(key)
        if base is None:
            raise KeyError(f"Unknown prompt key: {key}")
        return self.register_prompt(
            key=key,
            category=base.category,
            purpose=base.purpose,
            system_prompt=system_prompt,
            description=description or base.description,
            tags=tags or base.tags,
            active=active,
            metadata={**base.metadata, **(metadata or {})},
        )

    def get_prompt(self, key: str, version: Optional[int] = None, active_only: bool = True) -> Optional[PromptEntry]:
        versions = self._prompts.get(key, [])
        if not versions:
            return None

        if version is not None:
            for item in versions:
                if item.version == version:
                    if active_only and not item.active:
                        return None
                    return item
            return None

        candidates = [item for item in versions if item.active] if active_only else list(versions)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item.version, reverse=True)
        return candidates[0]

    def list_prompts(
        self,
        category: Optional[str] = None,
        purpose: Optional[str] = None,
        active_only: bool = True,
    ) -> List[PromptEntry]:
        out: List[PromptEntry] = []
        category_norm = category.strip().lower() if category else None
        purpose_norm = purpose.strip().lower() if purpose else None

        for entries in self._prompts.values():
            for item in entries:
                if active_only and not item.active:
                    continue
                if category_norm and item.category != category_norm:
                    continue
                if purpose_norm and item.purpose != purpose_norm:
                    continue
                out.append(item)

        out.sort(key=lambda item: (item.category, item.purpose, item.key, -item.version))
        return out

    def set_prompt_active(self, key: str, version: int, active: bool) -> bool:
        with self._lock:
            entries = self._prompts.get(key, [])
            for item in entries:
                if item.version == version:
                    item.active = active
                    item.updated_at = _utc_now()
                    self._persist()
                    return True
        return False

    def resolve_prompt(
        self,
        key: str,
        version: Optional[int] = None,
        include_rag_context: bool = False,
        rag_request: Optional[RagQueryRequest] = None,
        **kwargs: Any,
    ) -> PromptResolution:
        entry = self.get_prompt(key=key, version=version, active_only=True)
        if entry is None:
            raise KeyError(f"Prompt key not found: {key}")

        try:
            rendered = entry.system_prompt.format_map(_SafeDict(**{k: (v if v is not None else "") for k, v in kwargs.items()}))
        except Exception:
            rendered = entry.system_prompt

        metadata = dict(entry.metadata)
        if include_rag_context:
            request = rag_request or RagQueryRequest(query=str(kwargs.get("query") or ""), top_k=5)
            context_chunks = self.retrieve_context(request)
            if context_chunks:
                context_block = self._to_context_block(context_chunks)
                rendered = f"{rendered}\n\n[CONTEXT]\n{context_block}\n[/CONTEXT]"
                metadata["rag_context_asset_ids"] = [chunk.asset_id for chunk in context_chunks]

        return PromptResolution(
            key=entry.key,
            category=entry.category,
            purpose=entry.purpose,
            version=entry.version,
            prompt=rendered,
            prompt_id=entry.id,
            metadata=metadata,
        )

    # ---------------------------
    # Knowledge / RAG APIs
    # ---------------------------
    def register_knowledge_asset(
        self,
        asset_key: str,
        category: str,
        purpose: str,
        content: str,
        source_uri: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active: bool = True,
    ) -> KnowledgeAsset:
        with self._lock:
            existing = self._get_asset_by_key(asset_key)
            if existing:
                existing.category = category.strip().lower()
                existing.purpose = purpose.strip().lower()
                existing.content = content
                existing.source_uri = source_uri
                existing.tags = [tag.strip().lower() for tag in (tags or []) if tag and tag.strip()]
                existing.metadata = metadata or {}
                existing.active = active
                existing.updated_at = _utc_now()
                self._persist()
                return existing

            asset = KnowledgeAsset(
                id=str(uuid.uuid4()),
                asset_key=asset_key,
                category=category.strip().lower(),
                purpose=purpose.strip().lower(),
                content=content,
                source_uri=source_uri,
                tags=[tag.strip().lower() for tag in (tags or []) if tag and tag.strip()],
                metadata=metadata or {},
                active=active,
            )
            self._knowledge_assets[asset.id] = asset
            self._persist()
            return asset

    def list_knowledge_assets(
        self,
        category: Optional[str] = None,
        purpose: Optional[str] = None,
        active_only: bool = True,
    ) -> List[KnowledgeAsset]:
        category_norm = category.strip().lower() if category else None
        purpose_norm = purpose.strip().lower() if purpose else None

        out: List[KnowledgeAsset] = []
        for asset in self._knowledge_assets.values():
            if active_only and not asset.active:
                continue
            if category_norm and asset.category != category_norm:
                continue
            if purpose_norm and asset.purpose != purpose_norm:
                continue
            out.append(asset)

        out.sort(key=lambda item: (item.category, item.purpose, item.asset_key))
        return out

    def retrieve_context(self, request: RagQueryRequest) -> List[RagContextChunk]:
        return self.retriever.retrieve(request)

    # ---------------------------
    # Internal storage
    # ---------------------------
    def _ensure_storage(self) -> None:
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        if not os.path.exists(self.STORAGE_PATH):
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump({"prompts": {}, "knowledge_assets": []}, fh)

    def _load(self) -> None:
        try:
            with open(self.STORAGE_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return

        prompts = raw.get("prompts") if isinstance(raw, dict) else None
        if isinstance(prompts, dict):
            for key, versions in prompts.items():
                if not isinstance(versions, list):
                    continue
                parsed_versions: List[PromptEntry] = []
                for item in versions:
                    if isinstance(item, dict):
                        try:
                            parsed_versions.append(PromptEntry(**item))
                        except Exception:
                            continue
                if parsed_versions:
                    self._prompts[key] = parsed_versions

        assets = raw.get("knowledge_assets") if isinstance(raw, dict) else None
        if isinstance(assets, list):
            for item in assets:
                if isinstance(item, dict):
                    try:
                        asset = KnowledgeAsset(**item)
                        self._knowledge_assets[asset.id] = asset
                    except Exception:
                        continue

    def _persist(self) -> None:
        out = {
            "prompts": {key: [entry.__dict__ for entry in versions] for key, versions in self._prompts.items()},
            "knowledge_assets": [asset.__dict__ for asset in self._knowledge_assets.values()],
        }
        with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)

    def _load_defaults(self) -> None:
        defaults = {
            "system.recruitment.general": {
                "category": "recruitment",
                "purpose": "general_assistant",
                "prompt": "You are an enterprise AI recruitment copilot. Be accurate, explain trade-offs, and avoid unsupported claims.",
                "description": "General recruitment system prompt",
                "tags": ["system", "assistant"],
            },
            "system.recruitment.evaluation": {
                "category": "recruitment",
                "purpose": "candidate_evaluation",
                "prompt": "You are an AI evaluator. Produce structured, explainable, and bias-aware candidate assessments based only on provided evidence.",
                "description": "Evaluation system prompt",
                "tags": ["system", "evaluation"],
            },
            "system.recruitment.interview": {
                "category": "recruitment",
                "purpose": "interview_engine",
                "prompt": "You are an AI interview engine. Ask clear, role-relevant questions and adapt follow-ups based on candidate responses.",
                "description": "Interview engine system prompt",
                "tags": ["system", "interview"],
            },
        }

        if not self._prompts:
            for key, cfg in defaults.items():
                self.register_prompt(
                    key=key,
                    category=cfg["category"],
                    purpose=cfg["purpose"],
                    system_prompt=cfg["prompt"],
                    description=cfg["description"],
                    tags=cfg["tags"],
                )

    def _to_context_block(self, chunks: List[RagContextChunk]) -> str:
        lines: List[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            lines.append(f"{idx}. (score={chunk.score}) {chunk.content}")
        return "\n".join(lines)

    def _get_asset_by_key(self, asset_key: str) -> Optional[KnowledgeAsset]:
        for asset in self._knowledge_assets.values():
            if asset.asset_key == asset_key:
                return asset
        return None


DEFAULT_AI_KNOWLEDGE_PROMPT_REGISTRY = AIKnowledgePromptRegistry()
