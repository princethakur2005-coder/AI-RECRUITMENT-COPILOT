from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import os
import time
import uuid


@dataclass
class PromptVersion:
    id: str
    template: str
    description: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    active: bool = True
    weight: float = 1.0


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


class PromptManager:
    """Centralized prompt templates with versioning, metrics, and A/B testing support.

    Storage:
      - `data/prompts.json` stores templates and versions
      - `data/prompt_evaluations.jsonl` appends evaluation records for prompt runs
    """

    STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "prompts.json")
    EVAL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "prompt_evaluations.jsonl")

    def __init__(self) -> None:
        self._templates: Dict[str, List[PromptVersion]] = {}
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        if not os.path.exists(self.STORAGE_PATH):
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)
        open(self.EVAL_PATH, "a", encoding="utf-8").close()
        self._load_defaults()
        self._load_from_store()

    def _persist(self) -> None:
        out = {}
        for name, versions in self._templates.items():
            out[name] = [v.__dict__ for v in versions]
        with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)

    def _load_from_store(self) -> None:
        try:
            with open(self.STORAGE_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            for name, versions in raw.items():
                self._templates[name] = [PromptVersion(**v) for v in versions]
        except Exception:
            # ignore malformed store
            pass

    def _load_defaults(self) -> None:
        # Only populate defaults if not already present in store
        defaults = {
            "resume_summary": (
                "You are an expert recruitment analyst. Provide a concise summary of the"
                " candidate resume focusing on skills, experience, achievements, and role fit.\n"
                "Resume:\n{resume_text}\n\nReturn a summary in {max_tokens} tokens or fewer."
            ),
            "skill_match": (
                "Given the job requirements: {job_requirements}\nAnd the resume text: {resume_text}\n"
                "List matched skills, missing skills, and a short justification for each match."
            ),
            "candidate_ranking": (
                "Rank the following candidates for the role described by {job_description}.\n"
                "Use criteria: {criteria}. For each candidate provide a numeric score and a brief rationale.\n"
                "Candidates:\n{candidates}"
            ),
            "candidate_shortlist": (
                "As a hiring copilot, review the top candidates below for the role described by {job_description}.\n"
                "Use the criteria: {criteria}. Provide a shortlist of the top {top_n} candidates with a short rationale for each.\n"
                "Candidates:\n{candidates}"
            ),
            "compare_candidates": (
                "Compare these candidates for the role described by {job_description}.\n"
                "Highlight strengths, weaknesses, risks, and skill gaps for each candidate based on criteria: {criteria}.\n"
                "Recommend the best candidate and explain why they are the strongest fit.\n"
                "Candidates:\n{candidates}"
            ),
            "explain_decision": (
                "Explain this AI hiring decision in recruiter-friendly language.\n"
                "Decision context: {decision_context}\n"
                "Decision: {decision}\n"
                "Include why the AI made the recommendation and what factors matter most."
            ),
            "note_suggestion": (
                "You are an AI recruitment assistant. Suggest a short recruiter note for {candidate_name}."
                " Use the candidate summary and recruiter context to make it actionable."
                " If there are mention targets, include them with @handle syntax.\n"
                "Candidate summary: {candidate_summary}\n"
                "Recruiter context: {recruiter_context}\n"
                "Mentions: {mentions}\n"
                "Return only the suggested note content."
            ),
            "interview_questions": ("Generate {count} interview questions for the role: {role}. Focus on {focus}."),
        }

        for name, tpl in defaults.items():
            if name not in self._templates:
                self.add_template(name, tpl, description="default")

        # backward-compat short_bio default (keeps previous behavior)
        if "short_bio" not in self._templates:
            self.add_template(
                "short_bio",
                "Write a short professional bio for {name} that emphasizes {highlights}. Keep it under {max_tokens} tokens.",
                description="Create a short professional bio",
            )

    # Template/version operations
    def add_template(self, name: str, template: str, description: str = "", active: bool = True, weight: float = 1.0) -> PromptVersion:
        """Create a new named template (first version) or add a new version if exists."""
        ver = PromptVersion(id=str(uuid.uuid4()), template=template, description=description, active=active, weight=weight)
        if name not in self._templates:
            self._templates[name] = [ver]
        else:
            self._templates[name].append(ver)
        self._persist()
        return ver

    def add_template_version(self, name: str, template: str, description: str = "", active: bool = True, weight: float = 1.0) -> PromptVersion:
        return self.add_template(name, template, description=description, active=active, weight=weight)

    def list_versions(self, name: str) -> List[PromptVersion]:
        return list(self._templates.get(name, []))

    def get_version(self, name: str, version_id: Optional[str] = None) -> Optional[PromptVersion]:
        versions = self._templates.get(name, [])
        if not versions:
            return None
        if version_id:
            for v in versions:
                if v.id == version_id:
                    return v
            return None
        # return highest-weight active version or first active
        active = [v for v in versions if v.active]
        if not active:
            return versions[-1]
        # choose version by highest weight
        active.sort(key=lambda x: x.weight, reverse=True)
        return active[0]

    def set_version_active(self, name: str, version_id: str, active: bool = True) -> bool:
        versions = self._templates.get(name, [])
        for v in versions:
            if v.id == version_id:
                v.active = active
                self._persist()
                return True
        return False

    def set_version_weight(self, name: str, version_id: str, weight: float) -> bool:
        versions = self._templates.get(name, [])
        for v in versions:
            if v.id == version_id:
                v.weight = float(weight)
                self._persist()
                return True
        return False

    # Rendering with optional A/B selection
    def render(self, name: str, version_id: Optional[str] = None, ab_test: bool = False, **kwargs: Any) -> Dict[str, Any]:
        """Render a prompt; returns dict with `prompt`, `version_id`, and `template_meta`.

        If `ab_test` is True and multiple active versions exist, choose by weight probabilistically.
        """
        versions = self._templates.get(name)
        if not versions:
            raise KeyError(f"Unknown prompt template: {name}")

        chosen: PromptVersion
        if ab_test:
            active = [v for v in versions if v.active]
            if not active:
                chosen = versions[-1]
            elif len(active) == 1:
                chosen = active[0]
            else:
                # weighted random selection
                import random

                weights = [max(0.0, float(v.weight)) for v in active]
                total = sum(weights)
                if total <= 0:
                    chosen = random.choice(active)
                else:
                    r = random.random() * total
                    upto = 0.0
                    chosen = active[-1]
                    for v, w in zip(active, weights):
                        upto += w
                        if r <= upto:
                            chosen = v
                            break
        else:
            chosen = self.get_version(name, version_id=version_id) or versions[-1]

        try:
            prompt_text = chosen.template.format_map(_SafeDict(**{k: (v if v is not None else "") for k, v in kwargs.items()}))
        except Exception:
            prompt_text = chosen.template

        return {"prompt": prompt_text, "version_id": chosen.id, "template_meta": {"name": name, "description": chosen.description}}

    # Evaluation tracking
    def record_evaluation(self, template_name: str, version_id: str, input_kwargs: Dict[str, Any], ai_response: Any, outcome: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.EVAL_PATH), exist_ok=True)
        rec = {
            "id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "template": template_name,
            "version_id": version_id,
            "input": input_kwargs,
            "ai_response": ai_response,
            "outcome": outcome,
        }
        with open(self.EVAL_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# module-level manager for convenient reuse across the app
DEFAULT_PROMPT_MANAGER = PromptManager()

