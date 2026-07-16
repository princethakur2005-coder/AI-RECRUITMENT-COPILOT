from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from app.services.chat_service import ChatService
from app.services.resume_analysis import ResumeAnalysisService
from app.services.feedback_service import FeedbackAnalysisService


class AnalyticsService:
    """Reusable analytics service producing recruitment metrics and hiring insights.

    This service reuses existing AI infrastructure (ChatService/Gemini) to produce
    narrative insights while also computing deterministic metrics useful for dashboards.
    """

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)
        self.ras = ResumeAnalysisService(provider=provider)
        self.feedback = FeedbackAnalysisService(provider=provider)

    def generate_recruitment_analytics(self, candidates: List[Dict[str, Any]], jobs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Compute deterministic recruitment metrics and ask the AI for narrative insights.

        Deterministic outputs:
        - total_candidates
        - top_technical_skills
        - average_experience_entries
        - education_distribution

        AI outputs:
        - narrative_insights (string)

        Returns a combined dict containing both metrics and `raw_ai`.
        """
        total = len(candidates)

        tech_counter = Counter()
        edu_counter = Counter()
        exp_counts = []

        for c in candidates:
            structured = c.get("structured_resume")
            if structured is None:
                structured = self.ras.extract_structured(c.get("resume_text", "") or "")

            techs = structured.get("technical_skills") or []
            tech_counter.update([t.lower() for t in techs if isinstance(t, str)])

            ed = structured.get("education") or []
            if ed:
                # count degree or raw line
                first = ed[0]
                if isinstance(first, dict):
                    deg = first.get("degree") or "other"
                else:
                    deg = str(first)
                edu_counter.update([deg.lower()])

            exp = structured.get("experience") or []
            exp_counts.append(len(exp))

        avg_experience_entries = float(sum(exp_counts) / len(exp_counts)) if exp_counts else 0.0
        top_technical_skills = [k for k, _ in tech_counter.most_common(20)]

        metrics = {
            "total_candidates": total,
            "top_technical_skills": top_technical_skills,
            "average_experience_entries": round(avg_experience_entries, 2),
            "education_distribution": dict(edu_counter.most_common()),
        }

        # Build an AI prompt to generate narrative insights
        prompt_lines = ["Recruitment analytics summary:"]
        prompt_lines.append(f"Total candidates: {total}")
        prompt_lines.append(f"Top skills: {', '.join(top_technical_skills[:10])}")
        prompt_lines.append(f"Avg experience entries: {metrics['average_experience_entries']}")
        prompt_lines.append(f"Education distribution: {metrics['education_distribution']}")
        if jobs:
            prompt_lines.append(f"Jobs analyzed: {len(jobs)}")

        prompt = "\n".join(prompt_lines) + "\n\nProvide 3 concise hiring insights and 3 recommended actions for the recruiting team. Return JSON with keys 'insights' and 'recommendations'."

        ai_resp = self.chat.send_message(prompt)
        ai_content = ai_resp.get("content", "")

        narrative = {"insights": [], "recommendations": [], "raw_ai": ai_resp}
        try:
            parsed = ai_content and __import__("json").loads(ai_content)
            if isinstance(parsed, dict):
                narrative["insights"] = parsed.get("insights") or []
                narrative["recommendations"] = parsed.get("recommendations") or []
                narrative["raw_ai"] = ai_resp
        except Exception:
            # Fallback: wrap the AI text as a single insight
            if ai_content:
                narrative["insights"] = [ai_content.strip()]

        return {"metrics": metrics, "narrative": narrative}

    def hiring_insights_from_feedback(self, candidate_name: str, feedback_items: List[str]) -> Dict[str, Any]:
        """Analyze interview feedback and return structured hiring insights and recommendations."""
        analysis = self.feedback.analyze_feedback(feedback_items, candidate_name=candidate_name)

        # Build prompt for higher-level recommendations
        prompt = (
            f"Candidate: {candidate_name}\nFeedback summary score: {analysis.get('score')}\nStrengths: {analysis.get('strengths')}\nWeaknesses: {analysis.get('weaknesses')}\n"
            "Provide three actionable recommendations for the hiring manager and a hiring decision (hire|hold|no_hire) with brief rationale. Return JSON with keys 'decision', 'rationale', 'actions'."
        )

        ai_resp = self.chat.send_message(prompt)
        ai_content = ai_resp.get("content", "")

        result: Dict[str, Any] = {"analysis": analysis, "recommendation": {}, "raw_ai": ai_resp}
        try:
            parsed = ai_content and __import__("json").loads(ai_content)
            if isinstance(parsed, dict):
                result["recommendation"] = parsed
                result["raw_ai"] = ai_resp
                return result
        except Exception:
            pass

        # Fallback: produce simple recommendation based on score
        score = analysis.get("score", 0.0)
        if score >= 0.7:
            decision = "hire"
            rationale = "Feedback is predominantly positive."
            actions = ["Prepare offer", "Confirm references", "Discuss compensation"]
        elif score >= 0.4:
            decision = "hold"
            rationale = "Mixed feedback; consider follow-up interview."
            actions = ["Schedule technical follow-up", "Gather more feedback", "Check for cultural fit"]
        else:
            decision = "no_hire"
            rationale = "Feedback indicates gaps relative to the role."
            actions = ["Provide constructive feedback to candidate", "Keep resume for future roles"]

        result["recommendation"] = {"decision": decision, "rationale": rationale, "actions": actions}
        return result
