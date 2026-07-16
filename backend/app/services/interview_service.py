from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.utils.memo import memoize
from app.services.chat_service import ChatService
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER
from app.services.resume_analysis import ResumeAnalysisService

DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard", "Senior", "Architect"]


@dataclass
class InterviewQuestion:
    level: str
    text: str
    rubric: Dict[str, Any]


class InterviewService:
    """Service for generating interview questions and candidate summaries.

    Reuses existing AI infrastructure: `ChatService`, `PromptManager`, and
    `ResumeAnalysisService` (which in turn use the configured Gemini provider).
    """

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)
        self.ras = ResumeAnalysisService(provider=provider)

    @memoize(ttl=600, maxsize=2048)
    def generate_questions(
        self,
        job_description: Any,
        resume_text: Optional[str] = None,
        count: int = 5,
        focus: str = "technical",
        level: str = "Medium",
        missing_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate role-specific interview questions adapted to candidate strengths and gaps."""
        role = job_description.get("title") if isinstance(job_description, dict) else str(job_description)
        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        missing = ", ".join(missing_skills) if missing_skills else "none"

        prompt = (
            f"Generate {count} interview questions for the role: {role or 'role'}. "
            f"Difficulty: {level}. Focus on {focus}. "
            f"Job description: {job_text}. "
            f"Candidate resume context: {resume_text or 'not provided'}. "
            f"If the candidate has gaps in skills, adapt questions to probe those missing areas: {missing}. "
            "Return valid JSON with a `questions` array and include question difficulty and suggested evaluation rubric for each question."
        )

        resp = self.chat.send_message(prompt)
        content = resp.get("content", "") or ""

        questions: List[Dict[str, Any]] = []
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "questions" in parsed:
                questions = parsed.get("questions") or []
            elif isinstance(parsed, list):
                questions = parsed
        except Exception:
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                clean = re.sub(r"^\s*\d+[\).]?\s*", "", line)
                questions.append({"level": level, "text": clean, "rubric": self._default_rubric(level)})

        normalized: List[Dict[str, Any]] = []
        for q in questions:
            if isinstance(q, str):
                normalized.append({"level": level, "text": q, "rubric": self._default_rubric(level)})
            elif isinstance(q, dict):
                normalized.append(
                    {
                        "level": q.get("level") or level,
                        "text": q.get("text") or q.get("question") or "",
                        "rubric": q.get("rubric") or self._default_rubric(q.get("level") or level),
                    }
                )

        return {"questions": normalized, "raw": resp}

    def _default_rubric(self, level: str) -> Dict[str, Any]:
        score_scale = "0-5"
        if level == "Easy":
            return {"score_scale": score_scale, "guidance": "Clear understanding of fundamentals is expected."}
        if level == "Medium":
            return {"score_scale": score_scale, "guidance": "Effective problem solving with practical design and trade-offs."}
        if level == "Hard":
            return {"score_scale": score_scale, "guidance": "Strong technical depth, edge cases, and optimization insight."}
        if level == "Senior":
            return {"score_scale": score_scale, "guidance": "Architectural reasoning, leadership, and mentorship focus."}
        if level == "Architect":
            return {"score_scale": score_scale, "guidance": "System-level design, strategy, and long-term ownership."}
        return {"score_scale": score_scale, "guidance": "Provide a well-reasoned answer with examples."}

    @memoize(ttl=1800, maxsize=2048)
    def summarize_candidate(self, resume_text: str, max_tokens: int = 150) -> Dict[str, Any]:
        """Generate a concise candidate summary using prompts and the chat service."""
        prompt = DEFAULT_PROMPT_MANAGER.render("resume_summary", resume_text=resume_text, max_tokens=str(max_tokens))
        resp = self.chat.send_message(prompt)
        summary = resp.get("content", "") or ""
        # If AI returned JSON with a 'summary' field try to extract it
        try:
            parsed = json.loads(summary)
            if isinstance(parsed, dict) and "summary" in parsed:
                summary_text = parsed.get("summary") or ""
                return {"summary": summary_text, "raw": resp}
        except Exception:
            pass

        return {"summary": summary, "raw": resp}

    @memoize(ttl=600, maxsize=1024)
    def generate_interview_plan(
        self,
        job_description: Any,
        candidate_profile: Optional[Dict[str, Any]] = None,
        questions_per_level: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Generate an interview plan and role-specific questions at multiple difficulty levels."""
        questions_per_level = questions_per_level or {
            "Easy": 3,
            "Medium": 3,
            "Hard": 2,
            "Senior": 2,
            "Architect": 1,
        }

        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        role = job_description.get("title") if isinstance(job_description, dict) else None

        candidate_summary = ""
        candidate_skills = []
        missing_skills = []
        if candidate_profile:
            candidate_summary = candidate_profile.get("candidate_summary") or candidate_profile.get("summary") or ""
            candidate_skills = candidate_profile.get("profile", {}).get("technical_skills") or []
            missing_skills = candidate_profile.get("flags", [])
            if isinstance(missing_skills, list):
                missing_skills = [flag.get("field") for flag in missing_skills if flag.get("field") in {"technical_skills", "soft_skills", "experience", "education", "certifications", "projects"}]

        plan: Dict[str, Any] = {"stages": [], "questions_by_level": {}, "raw": {}}
        questions_by_level: Dict[str, List[Dict[str, Any]]] = {}

        for level in DIFFICULTY_LEVELS:
            count = questions_per_level.get(level, 0)
            if count <= 0:
                continue
            q_resp = self.generate_questions(
                job_description,
                resume_text=candidate_summary,
                count=count,
                focus="technical",
                level=level,
                missing_skills=missing_skills,
            )
            questions_by_level[level] = q_resp.get("questions") or []
            plan["raw"] = q_resp.get("raw")

        stages = [
            {"name": "Phone Screen", "questions": questions_by_level.get("Easy", [])},
            {"name": "Technical Screen", "questions": questions_by_level.get("Medium", []) + questions_by_level.get("Hard", [])},
            {"name": "Senior / Architect", "questions": questions_by_level.get("Senior", []) + questions_by_level.get("Architect", [])},
        ]

        plan["stages"] = stages
        plan["questions_by_level"] = questions_by_level
        return {"plan": plan, "raw": plan.get("raw")}

    def generate_evaluation_criteria(self, job_description: Any, role_level: str = "Mid") -> Dict[str, Any]:
        """Generate structured evaluation criteria and scoring rubrics for a role."""
        job_text = job_description.get("description") if isinstance(job_description, dict) else str(job_description)
        role = job_description.get("title") if isinstance(job_description, dict) else None
        normalized_level = role_level.title()

        prompt = (
            f"Create structured evaluation criteria and rubrics for hiring for role: {role or 'role'} "
            f"at experience level: {normalized_level}. Job description: {job_text}."
            "Focus each criterion on the candidate's ability to demonstrate competence, leadership, architectural judgment, and adaptation to missing skills."
            "Return valid JSON with keys: criteria (array of {name, description, weight}), rubric (mapping score->description), scoring_scale, and level." 
        )

        resp = self.chat.send_message(prompt)
        content = resp.get("content", "") or ""

        result = {"criteria": [], "rubric": {}, "scoring_scale": "0-5", "level": normalized_level, "raw": resp}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                result.update(parsed)
                result.setdefault("level", normalized_level)
                return result
        except Exception:
            pass

        # Fallback based on experience level
        base_criteria = [
            {"name": "Technical Skills", "description": "Depth and breadth of technical skills relevant to the role.", "weight": 0.4},
            {"name": "Problem Solving", "description": "Ability to reason through technical scenarios and arrive at practical solutions.", "weight": 0.25},
            {"name": "Communication", "description": "Clarity of explanation, collaboration, and ability to articulate trade-offs.", "weight": 0.15},
            {"name": "Culture Fit", "description": "Alignment with team values and company mission.", "weight": 0.1},
        ]

        if normalized_level in {"Senior", "Architect"}:
            base_criteria.append({"name": "Architecture & Leadership", "description": "Ability to design systems, guide teams, and make long-term technical decisions.", "weight": 0.25})
            base_criteria[0]["weight"] = 0.3
            base_criteria[1]["weight"] = 0.2
            base_criteria[2]["weight"] = 0.15
            base_criteria[3]["weight"] = 0.1
        elif normalized_level == "Hard":
            base_criteria.append({"name": "Design Depth", "description": "Quality of technical design and handling of complexity.", "weight": 0.15})
            base_criteria[0]["weight"] = 0.35
            base_criteria[1]["weight"] = 0.25
            base_criteria[2]["weight"] = 0.15
            base_criteria[3]["weight"] = 0.05
        elif normalized_level == "Easy":
            base_criteria[0]["weight"] = 0.45
            base_criteria[1]["weight"] = 0.2
            base_criteria[2]["weight"] = 0.2
            base_criteria[3]["weight"] = 0.15

        rubric = {
            "5": "Exceptional - demonstrates mastery with clear examples and strong judgment.",
            "4": "Strong - meets expectations with solid technical reasoning and few gaps.",
            "3": "Good - reasonable and adequate but may lack depth or polish.",
            "2": "Weak - shows partial understanding with significant gaps.",
            "1": "Poor - fails to demonstrate the required competency.",
            "0": "No evidence or incorrect response.",
        }

        return {"criteria": base_criteria, "rubric": rubric, "scoring_scale": "0-5", "level": normalized_level, "raw": resp}
