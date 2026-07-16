from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.utils.memo import memoize
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER
from app.services.ai_config import get_ai_config
from app.services.ai_provider import AIProvider, GeminiProvider


class BaseAIService:
    """Base service that can support multiple AI providers through dependency injection."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        if self.provider is None:
            return {
                "prompt": prompt,
                "content": "",
                "provider": None,
                "status": "not_configured",
            }
        return self.provider.generate(prompt, **kwargs)


class CandidateRankingEngine:
    """Reusable ranking engine for producing candidate scores from configurable criteria."""

    def __init__(self, criteria: dict[str, Any] | None = None) -> None:
        # Default weights: these are normalized contributions to the overall score
        defaults = {
            "skills_weight": 0.5,
            "experience_weight": 0.2,
            "education_weight": 0.1,
            "job_match_weight": 0.2,
        }
        self.criteria = {**defaults, **(criteria or {})}

    def score_candidate(self, candidate: dict[str, Any], job_description: str | None = None) -> dict[str, Any]:
        """Score a single candidate optionally against a job description.

        - `candidate` may include a `resume_text` or precomputed structured fields.
        - If `job_description` is provided the scoring incorporates job matching.
        """
        resume_text = candidate.get("resume_text", "") or ""

        # If structured resume exists, use it; otherwise run extraction heuristics
        structured = candidate.get("structured_resume")
        if structured is None:
            # instantiate a lightweight analysis service to extract structured resume
            ras = ResumeAnalysisService()
            structured = ras.extract_structured(resume_text)

        technical_skills = structured.get("technical_skills") or []
        soft_skills = structured.get("soft_skills") or []
        experience = structured.get("experience") or []
        education = structured.get("education") or []

        # Normalize component scores to 0..1
        skill_score = min(len(technical_skills) / 10.0, 1.0)  # assumes 10 skills ~ full
        experience_score = min(len(experience) / 10.0, 1.0)  # assumes 10 experience entries ~ full
        # education_score uses first education entry text if present
        education_text = ""
        if isinstance(education, list) and education:
            first = education[0]
            if isinstance(first, dict):
                education_text = first.get("degree") or ""
            else:
                education_text = str(first)
        education_score = self._score_education(education_text)

        job_match_score = 0.0
        matched_skills = []
        missing_skills = []
        if job_description:
            ras = ResumeAnalysisService()
            match = ras.match_structured_resume_to_job(structured, job_description)
            job_match_score = float(match.get("overall_score", 0.0))
            matched_skills = match.get("matched_skills", [])
            missing_skills = match.get("missing_skills", [])

        total_score = (
            skill_score * self.criteria.get("skills_weight", 0.0)
            + experience_score * self.criteria.get("experience_weight", 0.0)
            + education_score * self.criteria.get("education_weight", 0.0)
            + job_match_score * self.criteria.get("job_match_weight", 0.0)
        )

        return {
            "score": round(total_score, 3),
            "skill_score": round(skill_score, 3),
            "experience_score": round(experience_score, 3),
            "education_score": round(education_score, 3),
            "job_match_score": round(job_match_score, 3),
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "criteria": self.criteria,
            "structured_resume": structured,
        }

    def rank_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for candidate in candidates:
            scored = self.score_candidate(candidate)
            ranked.append({**candidate, **scored})

        ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ranked

    def rank_candidates_for_job(self, candidates: list[dict[str, Any]], job_description: str) -> list[dict[str, Any]]:
        """Score and rank candidates against a job description.

        Returns the candidates augmented with scoring details and sorted by `score`.
        """
        ranked = []
        for candidate in candidates:
            scored = self.score_candidate(candidate, job_description=job_description)
            ranked.append({**candidate, **scored})

        ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ranked

    def _score_skills(self, skills: list[str]) -> float:
        return float(min(len(skills), 5))

    def _score_experience(self, experience: Any) -> float:
        try:
            return float(experience)
        except (TypeError, ValueError):
            return 0.0

    def _score_education(self, education: str) -> float:
        if not education:
            return 0.0
        lowered = education.lower()
        if "master" in lowered or "phd" in lowered:
            return 2.0
        if "bachelor" in lowered or "bsc" in lowered or "ba" in lowered:
            return 1.5
        return 1.0


class ResumeAnalysisService(BaseAIService):
    """Reusable service for resume analysis and job matching."""

    def analyze(self, resume_text: str, job_requirements: list[str]) -> dict[str, Any]:
        normalized_resume = resume_text.lower()
        normalized_requirements = [requirement.lower() for requirement in job_requirements]

        matched_skills = [requirement for requirement in normalized_requirements if requirement in normalized_resume]
        score = self._score_resume(normalized_resume, normalized_requirements)

        return {
            "score": score,
            "matched_skills": matched_skills,
            "job_requirements": job_requirements,
            "match_rate": self._calculate_match_rate(score, len(normalized_requirements)),
            "summary": self._build_summary(score, matched_skills, len(normalized_requirements)),
        }

    def extract_structured(self, resume_text: str) -> dict[str, Any]:
        """Extract structured resume fields using AI provider (Gemini) when available.

        Returns a dict with keys: `technical_skills`, `soft_skills`, `education`,
        `experience`, `certifications`, `projects`, and `raw_ai` containing the
        provider response metadata.
        """
        return self._extract_structured_cached(resume_text)

    @memoize(ttl=1800, maxsize=2048)
    def _extract_structured_cached(self, resume_text: str) -> dict[str, Any]:
        # Build AI configuration for provider
        config = get_ai_config(provider="gemini")

        # Prefer injected provider, otherwise instantiate GeminiProvider with configured model
        provider = self.provider or GeminiProvider(model=config.model)

        # Render a summary prompt and append structured extraction instructions
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "resume_summary", resume_text=resume_text, max_tokens=str(config.max_tokens)
        )
        summary_prompt = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)

        extraction_instructions = (
            "Now extract the following fields from the resume and return a single valid JSON object:\n"
            "- technical_skills: array of strings\n"
            "- soft_skills: array of strings\n"
            "- education: array of objects with keys (degree, institution, start_year, end_year)\n"
            "- experience: array of objects with keys (title, company, start_year, end_year, description)\n"
            "- certifications: array of strings\n"
            "- projects: array of objects with keys (name, description, technologies)\n"
            "Only return the JSON object — do not add extra text."
        )

        prompt = f"{summary_prompt}\n\n{extraction_instructions}"

        ai_response = provider.generate(
            prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
        )

        raw_content = ai_response.get("content")

        structured: Dict[str, Any] = {
            "technical_skills": [],
            "soft_skills": [],
            "education": [],
            "experience": [],
            "certifications": [],
            "projects": [],
            "raw_ai": ai_response,
        }

        # Try to parse JSON if AI returned a JSON string
        if isinstance(raw_content, str) and raw_content.strip():
            try:
                parsed = json.loads(raw_content)
                if isinstance(parsed, dict):
                    # merge recognized keys only
                    for k in ("technical_skills", "soft_skills", "education", "experience", "certifications", "projects"):
                        if k in parsed:
                            structured[k] = parsed[k]
                    structured["raw_ai"] = ai_response
                    return structured
            except Exception:
                # fall through to heuristics
                pass

        # If AI did not return usable JSON, fall back to lightweight heuristics
        structured["technical_skills"] = self._extract_skills_heuristic(resume_text)
        structured["soft_skills"] = self._extract_soft_skills_heuristic(resume_text)
        structured["education"] = self._extract_education_heuristic(resume_text)
        structured["experience"] = self._extract_experience_heuristic(resume_text)
        structured["certifications"] = self._extract_certifications_heuristic(resume_text)
        structured["projects"] = self._extract_projects_heuristic(resume_text)

        return structured

    def analyze_job_description(self, job_description: str) -> dict[str, Any]:
        """Analyze a job description and extract required skills using AI (Gemini) or heuristics.

        Returns a dict with `required_skills` (list) and `raw_ai` metadata.
        """
        return self._analyze_job_description_cached(job_description)

    @memoize(ttl=1800, maxsize=1024)
    def _analyze_job_description_cached(self, job_description: str) -> dict[str, Any]:
        config = get_ai_config(provider="gemini")
        provider = self.provider or GeminiProvider(model=config.model)

        # Use skill_match template to focus on skills extraction
        rendered = DEFAULT_PROMPT_MANAGER.render("skill_match", job_requirements=job_description, resume_text="")
        prompt = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)

        extraction_instructions = (
            "From the job description, extract a JSON array named 'required_skills'"
            " containing the key technical and soft skills required. Return only JSON."
        )

        full_prompt = f"{prompt}\n\n{extraction_instructions}"

        ai_response = provider.generate(
            full_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
        )

        raw_content = ai_response.get("content")
        result: Dict[str, Any] = {"required_skills": [], "raw_ai": ai_response}

        if isinstance(raw_content, str) and raw_content.strip():
            try:
                parsed = json.loads(raw_content)
                # If AI returned an object with required_skills key
                if isinstance(parsed, dict) and "required_skills" in parsed:
                    result["required_skills"] = parsed.get("required_skills") or []
                    return result
                # If AI returned a list directly
                if isinstance(parsed, list):
                    result["required_skills"] = parsed
                    return result
            except Exception:
                pass

        # Heuristic fallback: look for Requirements/Qualifications sections
        skills = []
        for m in re.finditer(r"(?:requirements|qualifications|skills required)[:\-\n]\s*([\s\S]{0,300})", job_description, flags=re.I):
            block = m.group(1)
            parts = re.split(r"[,;\n]+", block)
            for p in parts:
                token = p.strip()
                if token:
                    skills.append(token)

        if not skills:
            tokens = re.findall(r"\b[A-Za-z+#]{2,20}\b", job_description)
            skills = list(dict.fromkeys(tokens))[:40]

        result["required_skills"] = skills
        return result

    def match_structured_resume_to_job(self, structured_resume: dict, job_description: str) -> dict[str, Any]:
        """Compare structured resume data to job description and produce compatibility data.

        Output contains: `required_skills`, `matched_skills`, `missing_skills`,
        `technical_match_rate`, `soft_match_rate`, and `overall_score`.
        """
        jd_analysis = self.analyze_job_description(job_description)
        required = [s.lower() for s in (jd_analysis.get("required_skills") or [])]

        tech = [s.lower() for s in (structured_resume.get("technical_skills") or [])]
        soft = [s.lower() for s in (structured_resume.get("soft_skills") or [])]

        matched = []
        matched_technical = []
        matched_soft = []

        for req in required:
            if any(req == t or req in t or t in req for t in tech):
                matched.append(req)
                matched_technical.append(req)
            elif any(req == s or req in s or s in req for s in soft):
                matched.append(req)
                matched_soft.append(req)

        missing = [r for r in required if r not in matched]

        total_required = len(required) or 1
        technical_match_rate = round(len(matched_technical) / total_required, 2)
        soft_match_rate = round(len(matched_soft) / total_required, 2)
        overall_score = round(len(matched) / total_required, 2)

        return {
            "required_skills": required,
            "matched_skills": matched,
            "missing_skills": missing,
            "technical_match_rate": technical_match_rate,
            "soft_match_rate": soft_match_rate,
            "overall_score": overall_score,
            "details": {
                "matched_technical": matched_technical,
                "matched_soft": matched_soft,
                "counts": {"required": len(required), "matched": len(matched)},
            },
            "raw_jd_ai": jd_analysis.get("raw_ai"),
        }

    def _extract_skills_heuristic(self, text: str) -> List[str]:
        # Look for a Skills: or Technical Skills: section
        skills = []
        for m in re.finditer(r"(?:skills|technical skills)[:\-\n]\s*([\s\S]{0,300})", text, flags=re.I):
            block = m.group(1).strip()
            # split by commas, semicolons, or newlines
            parts = re.split(r"[,;\n]+", block)
            for p in parts:
                token = p.strip()
                if token:
                    skills.append(token)
        # fallback: common technology tokens
        if not skills:
            tokens = re.findall(r"\b[A-Za-z+#]{2,20}\b", text)
            common_tech = [t for t in tokens if t.lower() not in ("the", "and", "for", "with")]
            skills = list(dict.fromkeys(common_tech))[:30]
        return skills

    def _extract_soft_skills_heuristic(self, text: str) -> List[str]:
        candidates = [
            "communication",
            "teamwork",
            "leadership",
            "problem solving",
            "adaptability",
            "time management",
            "creativity",
            "attention to detail",
        ]
        found = [s for s in candidates if re.search(r"\b" + re.escape(s) + r"\b", text, flags=re.I)]
        return found

    def _extract_education_heuristic(self, text: str) -> List[Dict[str, Optional[str]]]:
        ed = []
        for line in text.splitlines():
            if re.search(r"university|college|bachelor|master|phd|degree", line, flags=re.I):
                years = re.findall(r"(19|20)\d{2}", line)
                start = None
                end = None
                if years:
                    start = years[0]
                    if len(years) > 1:
                        end = years[1]
                ed.append({"degree": line.strip(), "institution": None, "start_year": start, "end_year": end})
        return ed

    def _extract_experience_heuristic(self, text: str) -> List[Dict[str, Optional[str]]]:
        ex = []
        # find lines with year ranges or 'at' patterns
        for line in text.splitlines():
            if re.search(r"\b(19|20)\d{2}\b", line) and (" at " in line.lower() or "@" in line):
                ex.append({"title": line.strip(), "company": None, "start_year": None, "end_year": None, "description": None})
        return ex

    def _extract_certifications_heuristic(self, text: str) -> List[str]:
        certs = []
        for line in text.splitlines():
            if re.search(r"certif", line, flags=re.I):
                certs.append(line.strip())
        return certs

    def _extract_projects_heuristic(self, text: str) -> List[Dict[str, Optional[str]]]:
        projects = []
        for m in re.finditer(r"project[:\-\n]\s*([\s\S]{0,200})", text, flags=re.I):
            name_desc = m.group(1).strip().split("\n", 1)
            name = name_desc[0].strip() if name_desc else ""
            desc = name_desc[1].strip() if len(name_desc) > 1 else ""
            projects.append({"name": name, "description": desc, "technologies": []})
        return projects

    def match_resume_to_job(self, resume_text: str, job_description: str) -> dict[str, Any]:
        resume_terms = self._tokenize(resume_text)
        job_terms = self._tokenize(job_description)
        overlap = sorted(set(resume_terms) & set(job_terms))
        score = len(overlap)

        return {
            "score": score,
            "matched_terms": overlap,
            "resume_terms": resume_terms,
            "job_terms": job_terms,
            "match_rate": self._calculate_match_rate(score, len(job_terms) or 1),
            "summary": self._build_summary(score, overlap, len(job_terms) or 1),
        }

    def rank_candidates(self, candidates: list[dict[str, Any]], job_requirements: list[str]) -> list[dict[str, Any]]:
        ranked = []
        for candidate in candidates:
            analysis = self.analyze(candidate.get("resume_text", ""), job_requirements)
            ranked.append({**candidate, **analysis})

        ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ranked

    def _score_resume(self, resume_text: str, requirements: list[str]) -> int:
        score = 0
        for requirement in requirements:
            if requirement in resume_text:
                score += 1
        return score

    def _calculate_match_rate(self, score: int, total: int) -> float:
        if total == 0:
            return 0.0
        return round(score / total, 2)

    def _build_summary(self, score: int, matched_items: list[str], total: int) -> str:
        if total == 0:
            return "No requirements provided"
        return f"Matched {score} of {total} items ({', '.join(matched_items) if matched_items else 'no overlaps'})"

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-zA-Z0-9#+.]+", text.lower()) if token]
