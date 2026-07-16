from __future__ import annotations

import re
from typing import Any, Dict, List

from app.services.resume_analysis import ResumeAnalysisService
from app.services.interview_service import InterviewService
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine


class CandidateProfileGenerator:
    """Generate structured candidate profiles with confidence scoring.

    Uses `ResumeAnalysisService` to extract resume fields and `InterviewService`
    to generate a concise summary. Confidence scores are heuristic-based and
    expressed as floats in range 0.0..1.0. Fields with confidence below 0.6
    are flagged as low confidence.
    """

    CONTACT_EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}")
    CONTACT_PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{6,}\d")

    def __init__(self, provider: Any | None = None) -> None:
        self.ras = ResumeAnalysisService(provider=provider)
        self.interview = InterviewService(provider=provider)
        self.intelligence = ResumeIntelligenceEngine()

    def generate_profile(self, resume_text: str) -> Dict[str, Any]:
        """Produce a candidate profile with extracted fields and confidence scores.

        Returns a dict containing `profile`, `confidences`, and `flags`.
        """
        structured = self.ras.extract_structured(resume_text)

        # Contact inference
        email = self._find_first(self.CONTACT_EMAIL_RE, resume_text)
        phone = self._find_first(self.CONTACT_PHONE_RE, resume_text)

        # Summary using interview service
        summary_resp = self.interview.summarize_candidate(resume_text, max_tokens=120)
        summary_text = summary_resp.get("summary") if isinstance(summary_resp, dict) else summary_resp

        intelligence = self.intelligence.build_intelligence(
            resume_text=resume_text,
            structured=structured,
            summary=summary_text or "",
            email=email,
            phone=phone,
        )

        canonical = intelligence.get("canonical") or {}
        basics = canonical.get("basics") or {}
        skills = canonical.get("skills") or {}

        profile: Dict[str, Any] = {
            "technical_skills": skills.get("technical") or [],
            "soft_skills": skills.get("soft") or [],
            "education": canonical.get("education") or [],
            "experience": canonical.get("experience") or [],
            "certifications": canonical.get("certifications") or [],
            "projects": canonical.get("projects") or [],
            "email": basics.get("email"),
            "phone": basics.get("phone"),
            "location": basics.get("location"),
            "current_title": basics.get("current_title"),
            "summary": basics.get("summary") or "",
        }

        confidences = intelligence.get("field_confidence_scores") or {}
        flags: List[Dict[str, str]] = []

        # Backward-compatible confidence and missing flags.
        for field, conf in list(confidences.items()):
            if conf < 0.6:
                flags.append({"field": field, "issue": f"low_confidence ({conf})"})
            if conf == 0.0:
                flags.append({"field": field, "issue": "missing"})

        # Include explicit inconsistency flags for downstream review flows.
        for issue in intelligence.get("inconsistencies") or []:
            issue_field = str(issue.get("field") or "resume")
            issue_name = str(issue.get("issue") or "inconsistent")
            flags.append({"field": issue_field, "issue": issue_name})

        return {
            "profile": profile,
            "confidences": confidences,
            "flags": flags,
            "raw_extraction": structured,
            "canonical_profile": canonical,
            "inconsistencies": intelligence.get("inconsistencies") or [],
            "employment_analysis": intelligence.get("employment_analysis") or {},
            "career_progression": intelligence.get("career_progression") or {},
            "ats_compatibility": intelligence.get("ats_compatibility_score") or {},
        }

    def _find_first(self, pattern: re.Pattern, text: str) -> str | None:
        m = pattern.search(text)
        return m.group(0).strip() if m else None
