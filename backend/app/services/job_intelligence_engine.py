from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.services.ai_config import get_ai_config
from app.services.ai_provider import AIProvider, AIProviderFactory
from app.services.resume_intelligence_engine import ResumeIntelligenceEngine


class JobIntelligenceEngine:
    """Build normalized job intelligence from unstructured job descriptions."""

    VALID_SENIORITY = {
        "intern": "intern",
        "junior": "junior",
        "mid": "mid",
        "senior": "senior",
        "lead": "lead",
        "staff": "staff",
        "principal": "principal",
        "manager": "manager",
        "director": "director",
        "executive": "executive",
    }

    def __init__(
        self,
        provider: AIProvider | None = None,
        provider_name: str = "gemini",
        normalizer: ResumeIntelligenceEngine | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.config = get_ai_config(provider=provider_name)
        self.provider = provider or AIProviderFactory.create(provider_name, model=self.config.model)
        self.normalizer = normalizer or ResumeIntelligenceEngine()

    def build_intelligence(self, job_description: str, title: str | None = None) -> dict[str, Any]:
        if not (job_description or "").strip():
            return self._empty_result()

        prompt = self._build_prompt(job_description=job_description, title=title)
        generated = self.provider.generate_structured(
            prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
        )

        parsed = generated.get("data")
        if not isinstance(parsed, dict):
            parsed = {}

        normalized = self._normalize_payload(parsed)
        normalized["metadata"] = {
            "source": "job_intelligence_engine",
            "provider": self.provider_name,
            "model": self.config.model,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }

        # Ensure summary is always present, even when AI returns partial data.
        if not normalized.get("summary"):
            normalized["summary"] = self._fallback_summary(job_description, normalized)

        return normalized

    def _build_prompt(self, job_description: str, title: str | None) -> str:
        role = (title or "").strip() or "Unknown Role"
        return (
            "You are an expert hiring analyst. "
            "Extract job intelligence from the job description below and return one valid JSON object only.\n\n"
            f"Role title: {role}\n"
            f"Job description:\n{job_description}\n\n"
            "JSON schema requirements:\n"
            "- required_skills: array[string]\n"
            "- preferred_skills: array[string]\n"
            "- technologies: array[string]\n"
            "- years_of_experience: string (for example: '3+ years', '5-7 years', 'Not specified')\n"
            "- seniority_level: one of [intern, junior, mid, senior, lead, staff, principal, manager, director, executive] when possible\n"
            "- education: array[string]\n"
            "- certifications: array[string]\n"
            "- responsibilities: array[string]\n"
            "- summary: short role summary in 2-4 sentences\n"
            "Rules:\n"
            "- Use empty arrays when unknown.\n"
            "- Do not hallucinate specific technologies not implied by text.\n"
            "- Keep values concise and recruiter-friendly.\n"
            "- Return JSON only."
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("required_skills")))
        preferred = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("preferred_skills")))
        technologies = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("technologies")))

        years_text = self._clean_text(payload.get("years_of_experience"))
        years_min, years_max = self._parse_experience_range(years_text)

        seniority = self._normalize_seniority(payload.get("seniority_level"))

        education = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("education")))
        certifications = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("certifications")))
        responsibilities = self.normalizer.normalize_terms(self._ensure_str_list(payload.get("responsibilities")))

        summary = self._clean_text(payload.get("summary")) or ""

        return {
            "required_skills": required,
            "preferred_skills": preferred,
            "technologies": technologies,
            "years_of_experience": {
                "text": years_text,
                "minimum": years_min,
                "maximum": years_max,
            },
            "seniority_level": seniority,
            "education": education,
            "certifications": certifications,
            "responsibilities": responsibilities,
            "summary": summary,
        }

    def _empty_result(self) -> dict[str, Any]:
        return {
            "required_skills": [],
            "preferred_skills": [],
            "technologies": [],
            "years_of_experience": {"text": None, "minimum": None, "maximum": None},
            "seniority_level": None,
            "education": [],
            "certifications": [],
            "responsibilities": [],
            "summary": "",
            "metadata": {
                "source": "job_intelligence_engine",
                "provider": self.provider_name,
                "model": self.config.model,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        }

    def _ensure_str_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in re.split(r"[,;\n]+", value) if part.strip()]
        return []

    def _parse_experience_range(self, years_text: str | None) -> tuple[int | None, int | None]:
        if not years_text:
            return None, None

        numbers = [int(match) for match in re.findall(r"\b(\d{1,2})\b", years_text)]
        if not numbers:
            return None, None

        if len(numbers) == 1:
            if "+" in years_text:
                return numbers[0], None
            return numbers[0], numbers[0]

        return min(numbers), max(numbers)

    def _normalize_seniority(self, value: Any) -> str | None:
        text = (self._clean_text(value) or "").lower()
        if not text:
            return None

        for key in self.VALID_SENIORITY:
            if key in text:
                return key

        return None

    def _fallback_summary(self, job_description: str, intelligence: dict[str, Any]) -> str:
        req_count = len(intelligence.get("required_skills") or [])
        pref_count = len(intelligence.get("preferred_skills") or [])
        responsibilities = intelligence.get("responsibilities") or []
        first_resp = responsibilities[0] if responsibilities else "deliver role outcomes"
        return (
            f"This role focuses on {first_resp}. "
            f"It emphasizes {req_count} required skills and {pref_count} preferred skills extracted from the description. "
            "Candidates should align with the listed technologies, experience expectations, and domain responsibilities."
        )

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return re.sub(r"\s+", " ", text) if text else None
