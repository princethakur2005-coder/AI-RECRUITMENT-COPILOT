from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.candidate import CandidateService
from app.services.job import JobService
from app.services.semantic_candidate_matching import SemanticCandidateMatchingService


@dataclass
class CandidateRankingWeights:
    required_skills: float = 0.35
    preferred_skills: float = 0.1
    experience: float = 0.2
    education: float = 0.1
    certifications: float = 0.1
    semantic_similarity: float = 0.15

    def normalized(self) -> CandidateRankingWeights:
        total = (
            max(0.0, self.required_skills)
            + max(0.0, self.preferred_skills)
            + max(0.0, self.experience)
            + max(0.0, self.education)
            + max(0.0, self.certifications)
            + max(0.0, self.semantic_similarity)
        )
        if total <= 0.0:
            return CandidateRankingWeights()

        return CandidateRankingWeights(
            required_skills=max(0.0, self.required_skills) / total,
            preferred_skills=max(0.0, self.preferred_skills) / total,
            experience=max(0.0, self.experience) / total,
            education=max(0.0, self.education) / total,
            certifications=max(0.0, self.certifications) / total,
            semantic_similarity=max(0.0, self.semantic_similarity) / total,
        )


@dataclass
class CandidateRankingRequest:
    job_id: str
    page: int = 1
    page_size: int = 20
    weights: CandidateRankingWeights | None = None
    semantic_matches: list[dict[str, Any]] | None = None
    execution_mode: str = "sync"


class CandidateRankingService:
    """Reusable candidate ranking service based on semantic match outputs."""

    def __init__(
        self,
        candidate_service: CandidateService,
        job_service: JobService,
        semantic_matching_service: SemanticCandidateMatchingService,
    ) -> None:
        self.candidate_service = candidate_service
        self.job_service = job_service
        self.semantic_matching_service = semantic_matching_service

    def rank_candidates_for_job(self, request: CandidateRankingRequest) -> dict[str, Any]:
        job = self.job_service.get_by_id(request.job_id)
        if job is None:
            raise ValueError("Job not found")

        weights = (request.weights or CandidateRankingWeights()).normalized()
        matches = self._resolve_semantic_matches(request.job_id, request.semantic_matches)

        ranked = []
        for match in matches:
            score_info = self._build_ranking_score(match, weights)
            ranked.append(
                {
                    "candidate_id": str(match.get("candidate_id")),
                    "job_id": str(match.get("job_id")),
                    "ranking_score": score_info["ranking_score"],
                    "match_score": int(match.get("match_score") or 0),
                    "missing_required_skills": match.get("missing_required_skills") or [],
                    "preferred_skills_possessed": match.get("preferred_skills_possessed") or [],
                    "explanation": self._recruiter_explanation(match, score_info),
                    "score_components": score_info["components"],
                    "confidence": score_info["confidence"],
                    "semantic_match": match,
                }
            )

        ranked.sort(key=lambda item: item.get("ranking_score", 0), reverse=True)
        for index, item in enumerate(ranked, start=1):
            item["ranking_position"] = index

        paged = self._paginate(ranked, request.page, request.page_size)
        return {
            "job_id": str(job.id),
            "job_title": job.title,
            "weights": {
                "required_skills": round(weights.required_skills, 4),
                "preferred_skills": round(weights.preferred_skills, 4),
                "experience": round(weights.experience, 4),
                "education": round(weights.education, 4),
                "certifications": round(weights.certifications, 4),
                "semantic_similarity": round(weights.semantic_similarity, 4),
            },
            "pagination": paged["pagination"],
            "items": paged["items"],
            "metadata": {
                "total_candidates_ranked": len(ranked),
                "execution": {
                    "mode": request.execution_mode,
                    "background_supported": True,
                    "background_enqueued": False,
                },
                "source": "candidate_ranking_service",
            },
        }

    def _resolve_semantic_matches(self, job_id: str, semantic_matches: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if semantic_matches is not None:
            return [item for item in semantic_matches if str(item.get("job_id")) == str(job_id)]

        candidates = self.candidate_service.get_all()
        results = []
        for candidate in candidates:
            result = self.semantic_matching_service.match_candidate_to_job(
                candidate_id=str(candidate.id),
                job_id=str(job_id),
            )
            results.append(result)
        return results

    def _build_ranking_score(self, semantic_match: dict[str, Any], weights: CandidateRankingWeights) -> dict[str, Any]:
        components = semantic_match.get("components") or []
        skills_component = self._get_component(components, "skills")
        experience_component = self._get_component(components, "experience")
        edu_cert_component = self._get_component(components, "education_certifications")
        semantic_component = self._get_component(components, "semantic_similarity")

        required_coverage = float((skills_component.get("explanation") or {}).get("required_coverage") or 0.0)
        preferred_coverage = float((skills_component.get("explanation") or {}).get("preferred_coverage") or 0.0)

        edu_exp = edu_cert_component.get("explanation") or {}
        edu_score = self._coverage(
            edu_exp.get("matched_education") or [],
            edu_exp.get("required_education") or [],
            fallback=0.7,
        )
        cert_score = self._coverage(
            edu_exp.get("matched_certifications") or [],
            edu_exp.get("required_certifications") or [],
            fallback=0.7,
        )

        experience_score = float(experience_component.get("score") or 0.0)
        semantic_score = float(semantic_component.get("score") or 0.0)

        weighted = {
            "required_skills": required_coverage * weights.required_skills,
            "preferred_skills": preferred_coverage * weights.preferred_skills,
            "experience": experience_score * weights.experience,
            "education": edu_score * weights.education,
            "certifications": cert_score * weights.certifications,
            "semantic_similarity": semantic_score * weights.semantic_similarity,
        }
        total = max(0.0, min(1.0, sum(weighted.values())))
        ranking_score = int(round(total * 100))

        confidence = self._merge_confidence(semantic_match, components)

        return {
            "ranking_score": ranking_score,
            "components": {
                "required_skills": round(required_coverage, 4),
                "preferred_skills": round(preferred_coverage, 4),
                "experience": round(experience_score, 4),
                "education": round(edu_score, 4),
                "certifications": round(cert_score, 4),
                "semantic_similarity": round(semantic_score, 4),
                "weighted_contributions": {k: round(v, 4) for k, v in weighted.items()},
            },
            "confidence": confidence,
        }

    def _coverage(self, matched: list[Any], required: list[Any], fallback: float) -> float:
        req_count = len(required)
        if req_count == 0:
            return fallback
        return len(matched) / req_count

    def _merge_confidence(self, semantic_match: dict[str, Any], components: list[dict[str, Any]]) -> dict[str, Any]:
        semantic_conf = semantic_match.get("confidence") or {}
        base = float(semantic_conf.get("overall") or 0.0)

        per_component = [float(item.get("confidence") or 0.0) for item in components]
        component_avg = sum(per_component) / max(1, len(per_component)) if per_component else 0.0
        final = max(0.0, min(1.0, 0.55 * base + 0.45 * component_avg))

        return {
            "overall": round(final, 4),
            "semantic_match_confidence": round(base, 4),
            "component_confidence": round(component_avg, 4),
        }

    def _recruiter_explanation(self, semantic_match: dict[str, Any], score_info: dict[str, Any]) -> dict[str, Any]:
        missing_required = semantic_match.get("missing_required_skills") or []
        preferred = semantic_match.get("preferred_skills_possessed") or []
        score = score_info.get("ranking_score") or 0

        fit_label = "Strong fit" if score >= 80 else "Moderate fit" if score >= 60 else "Limited fit"

        highlights = []
        if preferred:
            highlights.append(f"Preferred skills matched: {', '.join(preferred[:5])}")
        if missing_required:
            highlights.append(f"Missing required skills: {', '.join(missing_required[:5])}")
        if not highlights:
            highlights.append("Core requirements are generally aligned based on available data.")

        return {
            "fit_label": fit_label,
            "summary": f"{fit_label} with ranking score {score}/100.",
            "highlights": highlights,
        }

    def _get_component(self, components: list[dict[str, Any]], name: str) -> dict[str, Any]:
        for item in components:
            if item.get("name") == name:
                return item
        return {}

    def _paginate(self, items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, int(page_size))
        total = len(items)
        total_pages = (total + normalized_page_size - 1) // normalized_page_size if total else 0

        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        page_items = items[start:end]

        return {
            "items": page_items,
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": total,
                "pages": total_pages,
            },
        }
