from __future__ import annotations

from typing import Any, Dict, List

from app.services.candidate_profile import CandidateProfileGenerator
from app.services.resume_analysis import ResumeAnalysisService
from app.services.chat_service import ChatService


class RankingInsightsService:
    """Produce explainable candidate ranking insights for recruiters.

    For each candidate the service returns why they received their score,
    strengths, weaknesses, missing skills and actionable recommendations.
    """

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.profile_gen = CandidateProfileGenerator(provider=provider)
        self.ras = ResumeAnalysisService(provider=provider)
        self.chat = ChatService(provider=provider, provider_name=provider_name)

    def explain_candidate(self, candidate: Dict[str, Any], job_description: Any) -> Dict[str, Any]:
        """Return an explanation for a single candidate relative to a job.

        Input candidate may be raw or enriched (contain `structured_resume` or `scoring`).
        """
        # Ensure structured profile and confidences
        structured = candidate.get("structured_resume")
        if structured is None:
            structured = self.ras.extract_structured(candidate.get("resume_text", "") or "")

        profile_result = self.profile_gen.generate_profile(candidate.get("resume_text", "") or "")
        profile = profile_result.get("profile", {})
        confidences = profile_result.get("confidences", {})
        flags = profile_result.get("flags", [])

        # Job analysis
        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        jd_analysis = self.ras.analyze_job_description(job_text)
        required_skills = [s.lower() for s in (jd_analysis.get("required_skills") or [])]

        technical = [t.lower() for t in (profile.get("technical_skills") or [])]
        soft = [s.lower() for s in (profile.get("soft_skills") or [])]

        matched = []
        matched_technical = []
        matched_soft = []
        for req in required_skills:
            if any(req == t or req in t or t in req for t in technical):
                matched.append(req)
                matched_technical.append(req)
            elif any(req == s or req in s or s in req for s in soft):
                matched.append(req)
                matched_soft.append(req)

        missing = [r for r in required_skills if r not in matched]

        # Score provenance: prefer existing scoring if present
        scoring = candidate.get("scoring") or candidate.get("score") or {}

        explanation = {
            "candidate_id": candidate.get("id") or candidate.get("email") or None,
            "score": scoring.get("score") if isinstance(scoring, dict) else scoring,
            "matched_skills": matched,
            "missing_skills": missing,
            "matched_technical": matched_technical,
            "matched_soft": matched_soft,
            "confidences": confidences,
            "flags": flags,
        }

        # Strengths heuristic
        strengths = []
        if matched_technical:
            strengths.append(f"Strong technical match: {', '.join(matched_technical[:5])}")
        if profile.get("experience"):
            strengths.append(f"Relevant experience entries: {len(profile.get('experience'))}")
        if profile.get("education"):
            strengths.append(f"Education present: {profile.get('education')[0]}")

        # Weaknesses heuristic
        weaknesses = []
        if missing:
            weaknesses.append(f"Missing required skills: {', '.join(missing[:8])}")
        low_conf = [f['field'] for f in flags if 'low_confidence' in f.get('issue', '')]
        if low_conf:
            weaknesses.append(f"Low confidence fields: {', '.join(low_conf)}")

        # Recommendations heuristic
        recommendations = []
        if missing:
            recommendations.append("Technical follow-up focusing on missing skills or assess via a skills test")
        if confidences.get("experience", 0) < 0.4:
            recommendations.append("Ask for more detailed work history or conduct a behavioral interview")
        if not missing and confidences.get("technical_skills", 0) > 0.7:
            recommendations.append("Consider advancing to on-site interview or offer discussion")

        explanation["strengths"] = strengths
        explanation["weaknesses"] = weaknesses
        explanation["recommendations"] = recommendations

        # Generate recruiter-friendly summary via AI for readability
        prompt = (
            f"Provide a short recruiter-friendly explanation for candidate: {candidate.get('id') or candidate.get('email')}."
            f"Score: {explanation.get('score')}\nStrengths: {strengths}\nWeaknesses: {weaknesses}\nRecommendations: {recommendations}\n"
            "Return a concise paragraph suitable for a recruiter dashboard."
        )

        ai_resp = self.chat.send_message(prompt)
        explanation["summary"] = ai_resp.get("content")
        explanation["raw_ai"] = ai_resp

        return explanation

    def explain_ranked(self, ranked_candidates: List[Dict[str, Any]], job_description: Any) -> List[Dict[str, Any]]:
        """Explain a list of ranked candidates, returning recruiter-friendly insights per candidate."""
        results = []
        for cand in ranked_candidates:
            res = self.explain_candidate(cand, job_description)
            results.append(res)
        return results
