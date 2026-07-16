from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Protocol

from app.services.candidate import CandidateService
from app.services.embedding_service import EmbeddingService, HashEmbeddingProvider
from app.services.job import JobService
from app.services.job_intelligence_engine import JobIntelligenceEngine
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine
from app.services.vector_store import InMemoryVectorStore, VectorRecord, VectorStore


@dataclass
class FactorResult:
    name: str
    score: float
    weight: float
    confidence: float
    explanation: dict[str, Any]


@dataclass
class MatchingContext:
    candidate_id: str
    job_id: str
    candidate_intelligence: dict[str, Any]
    job_intelligence: dict[str, Any]


class MatchingFactor(Protocol):
    name: str
    weight: float

    def evaluate(self, context: MatchingContext) -> FactorResult:
        raise NotImplementedError


class SkillsMatchingFactor:
    name = "skills"

    def __init__(self, weight: float = 0.45) -> None:
        self.weight = weight

    def evaluate(self, context: MatchingContext) -> FactorResult:
        candidate_skills = self._candidate_skills(context.candidate_intelligence)
        required = self._normalize(context.job_intelligence.get("required_skills") or [])
        preferred = self._normalize(context.job_intelligence.get("preferred_skills") or [])

        matched_required = sorted([skill for skill in required if skill in candidate_skills])
        missing_required = sorted([skill for skill in required if skill not in candidate_skills])
        matched_preferred = sorted([skill for skill in preferred if skill in candidate_skills])

        req_coverage = len(matched_required) / max(1, len(required))
        pref_coverage = len(matched_preferred) / max(1, len(preferred)) if preferred else 0.0
        score = min(1.0, 0.85 * req_coverage + 0.15 * pref_coverage)

        confidence = 0.9 if required else 0.6

        return FactorResult(
            name=self.name,
            score=round(score, 4),
            weight=self.weight,
            confidence=confidence,
            explanation={
                "required_skills": sorted(required),
                "preferred_skills": sorted(preferred),
                "matched_required_skills": matched_required,
                "missing_required_skills": missing_required,
                "matched_preferred_skills": matched_preferred,
                "required_coverage": round(req_coverage, 4),
                "preferred_coverage": round(pref_coverage, 4),
            },
        )

    def _candidate_skills(self, candidate_intelligence: dict[str, Any]) -> set[str]:
        canonical = candidate_intelligence.get("canonical") or {}
        skills = canonical.get("skills") or {}
        technical = self._normalize(skills.get("technical") or [])
        soft = self._normalize(skills.get("soft") or [])
        return set(technical) | set(soft)

    def _normalize(self, values: list[Any]) -> list[str]:
        normalized = []
        seen = set()
        for value in values:
            text = str(value).strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized


class ExperienceMatchingFactor:
    name = "experience"

    def __init__(self, weight: float = 0.2) -> None:
        self.weight = weight

    def evaluate(self, context: MatchingContext) -> FactorResult:
        candidate_years = float(
            ((context.candidate_intelligence.get("employment_analysis") or {}).get("total_experience_years") or 0.0)
        )
        years_req = context.job_intelligence.get("years_of_experience") or {}
        min_years = years_req.get("minimum")
        max_years = years_req.get("maximum")

        if min_years is None and max_years is None:
            score = 0.65
            confidence = 0.55
        elif min_years is not None and candidate_years < float(min_years):
            score = max(0.0, candidate_years / max(1.0, float(min_years)))
            confidence = 0.85
        elif max_years is not None and candidate_years > float(max_years):
            score = 0.9
            confidence = 0.8
        else:
            score = 1.0
            confidence = 0.9

        return FactorResult(
            name=self.name,
            score=round(score, 4),
            weight=self.weight,
            confidence=confidence,
            explanation={
                "candidate_total_years": round(candidate_years, 2),
                "job_minimum_years": min_years,
                "job_maximum_years": max_years,
            },
        )


class EducationCertificationFactor:
    name = "education_certifications"

    def __init__(self, weight: float = 0.15) -> None:
        self.weight = weight

    def evaluate(self, context: MatchingContext) -> FactorResult:
        canonical = context.candidate_intelligence.get("canonical") or {}
        candidate_education = [
            str((item or {}).get("degree") or "").strip().lower() for item in (canonical.get("education") or [])
        ]
        candidate_certs = [
            str((item or {}).get("name") or "").strip().lower() for item in (canonical.get("certifications") or [])
        ]

        required_education = [str(item).strip().lower() for item in (context.job_intelligence.get("education") or [])]
        required_certs = [str(item).strip().lower() for item in (context.job_intelligence.get("certifications") or [])]

        edu_matches = [item for item in required_education if self._contains_any(item, candidate_education)]
        cert_matches = [item for item in required_certs if self._contains_any(item, candidate_certs)]

        edu_score = len(edu_matches) / max(1, len(required_education)) if required_education else 0.7
        cert_score = len(cert_matches) / max(1, len(required_certs)) if required_certs else 0.7
        score = min(1.0, 0.6 * edu_score + 0.4 * cert_score)
        confidence = 0.8 if (required_education or required_certs) else 0.55

        return FactorResult(
            name=self.name,
            score=round(score, 4),
            weight=self.weight,
            confidence=confidence,
            explanation={
                "required_education": required_education,
                "matched_education": edu_matches,
                "required_certifications": required_certs,
                "matched_certifications": cert_matches,
            },
        )

    def _contains_any(self, requirement: str, candidate_values: list[str]) -> bool:
        return any(requirement in value or value in requirement for value in candidate_values if value)


class SemanticSimilarityFactor:
    name = "semantic_similarity"

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore, weight: float = 0.2) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.weight = weight

    def evaluate(self, context: MatchingContext) -> FactorResult:
        candidate_text = self._candidate_text(context.candidate_intelligence)
        job_text = self._job_text(context.job_intelligence)

        if not candidate_text or not job_text:
            return FactorResult(
                name=self.name,
                score=0.5,
                weight=self.weight,
                confidence=0.35,
                explanation={"reason": "insufficient_text_for_semantic_similarity"},
            )

        vectors = self.embedding_service.embed_texts([candidate_text, job_text])
        if len(vectors) != 2:
            return FactorResult(
                name=self.name,
                score=0.5,
                weight=self.weight,
                confidence=0.2,
                explanation={"reason": "embedding_generation_failed"},
            )

        candidate_vector = vectors[0]
        job_vector = vectors[1]

        self.vector_store.upsert(
            [
                VectorRecord(
                    id=f"candidate:{context.candidate_id}",
                    namespace="semantic_matching",
                    source_id=context.candidate_id,
                    content=candidate_text,
                    embedding=candidate_vector,
                    metadata={"entity": "candidate", "candidate_id": context.candidate_id},
                ),
                VectorRecord(
                    id=f"job:{context.job_id}",
                    namespace="semantic_matching",
                    source_id=context.job_id,
                    content=job_text,
                    embedding=job_vector,
                    metadata={"entity": "job", "job_id": context.job_id},
                ),
            ]
        )

        nearest = self.vector_store.query(
            namespace="semantic_matching",
            embedding=candidate_vector,
            top_k=1,
            filters={"entity": "job", "job_id": context.job_id},
        )

        similarity = float(nearest[0].score) if nearest else self._cosine(candidate_vector, job_vector)
        score = max(0.0, min(1.0, similarity))

        return FactorResult(
            name=self.name,
            score=round(score, 4),
            weight=self.weight,
            confidence=0.8,
            explanation={"semantic_similarity": round(score, 4)},
        )

    def _candidate_text(self, candidate_intelligence: dict[str, Any]) -> str:
        canonical = candidate_intelligence.get("canonical") or {}
        skills = canonical.get("skills") or {}
        technical = skills.get("technical") or []
        soft = skills.get("soft") or []
        title = (canonical.get("basics") or {}).get("current_title") or ""
        return " ".join([title] + [str(x) for x in technical] + [str(x) for x in soft]).strip()

    def _job_text(self, job_intelligence: dict[str, Any]) -> str:
        parts = []
        parts.extend([str(x) for x in (job_intelligence.get("required_skills") or [])])
        parts.extend([str(x) for x in (job_intelligence.get("preferred_skills") or [])])
        parts.extend([str(x) for x in (job_intelligence.get("technologies") or [])])
        parts.append(str(job_intelligence.get("summary") or ""))
        return " ".join(parts).strip()

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)


class SemanticCandidateMatchingService:
    """Composable semantic+structured candidate matching service."""

    def __init__(
        self,
        candidate_service: CandidateService,
        job_service: JobService,
        resume_intelligence_engine: ResumeIntelligenceEngine | None = None,
        job_intelligence_engine: JobIntelligenceEngine | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        factors: list[MatchingFactor] | None = None,
    ) -> None:
        self.candidate_service = candidate_service
        self.job_service = job_service
        self.resume_intelligence_engine = resume_intelligence_engine or ResumeIntelligenceEngine()
        self.job_intelligence_engine = job_intelligence_engine or JobIntelligenceEngine()
        self.embedding_service = embedding_service or EmbeddingService(provider=HashEmbeddingProvider())
        self.vector_store = vector_store or InMemoryVectorStore()
        self.factors = factors or [
            SkillsMatchingFactor(),
            ExperienceMatchingFactor(),
            EducationCertificationFactor(),
            SemanticSimilarityFactor(self.embedding_service, self.vector_store),
        ]

    def match_candidate_to_job(
        self,
        candidate_id: str,
        job_id: str,
        candidate_resume_intelligence: dict[str, Any] | None = None,
        job_intelligence: dict[str, Any] | None = None,
        candidate_resume_text: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.candidate_service.get_by_id(candidate_id)
        job = self.job_service.get_by_id(job_id)
        if candidate is None:
            raise ValueError("Candidate not found")
        if job is None:
            raise ValueError("Job not found")

        resolved_candidate_intelligence = candidate_resume_intelligence or self._resolve_candidate_intelligence(
            candidate,
            candidate_resume_text,
        )
        resolved_job_intelligence = job_intelligence or self._resolve_job_intelligence(job)

        context = MatchingContext(
            candidate_id=str(candidate.id),
            job_id=str(job.id),
            candidate_intelligence=resolved_candidate_intelligence,
            job_intelligence=resolved_job_intelligence,
        )

        results = [factor.evaluate(context) for factor in self.factors]
        total_weight = sum(max(0.0, item.weight) for item in results) or 1.0
        weighted_score = sum(item.score * item.weight for item in results) / total_weight
        normalized_score = int(round(max(0.0, min(1.0, weighted_score)) * 100))

        confidence = self._confidence(results, resolved_candidate_intelligence, resolved_job_intelligence)
        skill_component = next((item for item in results if item.name == "skills"), None)
        missing_required = (skill_component.explanation.get("missing_required_skills") if skill_component else []) or []
        matched_preferred = (skill_component.explanation.get("matched_preferred_skills") if skill_component else []) or []

        return {
            "candidate_id": str(candidate.id),
            "job_id": str(job.id),
            "match_score": normalized_score,
            "score_scale": "0-100",
            "missing_required_skills": missing_required,
            "preferred_skills_possessed": matched_preferred,
            "components": [
                {
                    "name": item.name,
                    "weight": round(item.weight, 4),
                    "score": round(item.score, 4),
                    "weighted_contribution": round(item.score * item.weight, 4),
                    "confidence": round(item.confidence, 4),
                    "explanation": item.explanation,
                }
                for item in results
            ],
            "confidence": confidence,
        }

    def _resolve_candidate_intelligence(self, candidate: Any, candidate_resume_text: str | None) -> dict[str, Any]:
        # Graceful fallback when rich resume data is unavailable.
        structured = {
            "technical_skills": self._split_csv(getattr(candidate, "skills", None)),
            "soft_skills": [],
            "education": [],
            "experience": [],
            "certifications": [],
            "projects": [],
        }

        summary = str(getattr(candidate, "summary", "") or "")
        resume_text = candidate_resume_text or summary
        return self.resume_intelligence_engine.build_intelligence(
            resume_text=resume_text,
            structured=structured,
            summary=summary,
            full_name=getattr(candidate, "full_name", None),
            email=getattr(candidate, "email", None),
            phone=getattr(candidate, "phone", None),
        )

    def _resolve_job_intelligence(self, job: Any) -> dict[str, Any]:
        existing = getattr(job, "job_intelligence", None)
        if isinstance(existing, dict) and existing:
            return existing

        return self.job_intelligence_engine.build_intelligence(
            job_description=str(getattr(job, "description", "") or ""),
            title=str(getattr(job, "title", "") or ""),
        )

    def _confidence(
        self,
        factors: list[FactorResult],
        candidate_intelligence: dict[str, Any],
        job_intelligence: dict[str, Any],
    ) -> dict[str, Any]:
        factor_conf = sum(item.confidence for item in factors) / max(1, len(factors))

        field_conf = candidate_intelligence.get("field_confidence_scores") or {}
        field_values = [float(v) for v in field_conf.values()] if isinstance(field_conf, dict) else []
        candidate_conf = sum(field_values) / max(1, len(field_values)) if field_values else 0.5

        job_fields = [
            job_intelligence.get("required_skills") or [],
            job_intelligence.get("preferred_skills") or [],
            job_intelligence.get("technologies") or [],
            (job_intelligence.get("years_of_experience") or {}).get("text"),
            job_intelligence.get("responsibilities") or [],
        ]
        present = sum(1 for field in job_fields if field)
        job_completeness = present / len(job_fields)

        combined = max(0.0, min(1.0, 0.45 * factor_conf + 0.35 * candidate_conf + 0.2 * job_completeness))
        return {
            "overall": round(combined, 4),
            "factor_confidence": round(factor_conf, 4),
            "candidate_data_confidence": round(candidate_conf, 4),
            "job_data_completeness": round(job_completeness, 4),
        }

    def _split_csv(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in str(value).split(",") if item.strip()]
