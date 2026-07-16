from __future__ import annotations

import json
from typing import Any, Dict

from app.services.interview_service import InterviewService
from app.services.resume_analysis import BaseAIService
from app.services.chat_service import ChatService
from app.services.ai_config import get_ai_config
from app.services.audit_service import audit_service
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER


class RecruiterAssistantService(BaseAIService):
    """Service layer for recruiter Q&A and hiring assistance.

    Uses a reusable `ChatService` that delegates to the configured Gemini provider.
    """

    def __init__(self, provider: Any | None = None) -> None:
        super().__init__(provider=provider)
        # Initialize a chat service; if a provider is injected, reuse it
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)
        self.interview_service = InterviewService(provider=provider)

    def answer_question(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        rendered = DEFAULT_PROMPT_MANAGER.render("short_bio", name=question, highlights=context.get("highlights", ""))
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        # Fall back to a simple constructed prompt if template not relevant
        if not prompt_text:
            prompt_text = f"Recruiter question: {question}\nContext: {', '.join(f'{k}={v}' for k, v in context.items()) or 'none'}"

        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "answer_question",
            "question": question,
            "answer": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
            "context": context,
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_question_answered",
            resource_type="system",
            resource_id=None,
            metadata={"question": question, "answer_preview": str(result["answer"])[:120]},
        )
        return result

    def assist_hiring(self, candidate_profile: dict[str, Any], job_description: dict[str, Any]) -> dict[str, Any]:
        # Build a hiring prompt using prompt manager candidate_ranking template
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "candidate_ranking",
            job_description=job_description.get("description", str(job_description)),
            criteria=job_description.get("criteria", "skills, experience"),
            candidates=candidate_profile,
        )
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)

        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "assist_hiring",
            "candidate_profile": candidate_profile,
            "job_description": job_description,
            "recommendation": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_hiring_assistance",
            resource_type="system",
            resource_id=None,
            metadata={"job_description": job_description, "candidate_count": len(candidate_profile) if isinstance(candidate_profile, list) else 0},
        )
        return result

    def shortlist_candidates(
        self,
        candidates: list[dict[str, Any]],
        job_description: dict[str, Any],
        top_n: int = 5,
    ) -> dict[str, Any]:
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "candidate_shortlist",
            job_description=job_description.get("description", str(job_description)),
            criteria=job_description.get("criteria", "skills, experience"),
            candidates=json.dumps(candidates, ensure_ascii=False, indent=2),
            top_n=str(top_n),
        )
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "shortlist_candidates",
            "top_n": top_n,
            "recommendation": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_shortlist_candidates",
            resource_type="system",
            resource_id=None,
            metadata={"top_n": top_n, "candidate_count": len(candidates)},
        )
        return result

    def compare_candidates(
        self,
        candidates: list[dict[str, Any]],
        job_description: dict[str, Any],
    ) -> dict[str, Any]:
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "compare_candidates",
            job_description=job_description.get("description", str(job_description)),
            criteria=job_description.get("criteria", "skills, experience"),
            candidates=json.dumps(candidates, ensure_ascii=False, indent=2),
        )
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "compare_candidates",
            "recommendation": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_compare_candidates",
            resource_type="system",
            resource_id=None,
            metadata={"candidate_count": len(candidates)},
        )
        return result

    def summarize_resume(self, resume_text: str, max_tokens: int = 200) -> dict[str, Any]:
        rendered = DEFAULT_PROMPT_MANAGER.render("resume_summary", resume_text=resume_text, max_tokens=str(max_tokens))
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "summarize_resume",
            "summary": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_summarize_resume",
            resource_type="system",
            resource_id=None,
            metadata={"summary_length": len(result["summary"])},
        )
        return result

    def create_interview_plan(
        self,
        job_description: dict[str, Any],
        candidate_profile: dict[str, Any] | None = None,
        questions_per_level: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        plan = self.assist_hiring(candidate_profile or {}, job_description) if candidate_profile else {}
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "interview_questions",
            count=str(sum(questions_per_level.values())) if questions_per_level else "5",
            role=job_description.get("title", "role") if isinstance(job_description, dict) else str(job_description),
            focus="technical and behavioral",
        )
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        self.chat.send_message(prompt_text)

        result = self.interview_service.generate_interview_plan(
            job_description=job_description,
            candidate_profile=candidate_profile,
            questions_per_level=questions_per_level,
        )
        output = {
            "action": "generate_interview_plan",
            "plan": result.get("plan"),
            "raw": result.get("raw"),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_generate_interview_plan",
            resource_type="system",
            resource_id=None,
            metadata={"job_title": job_description.get("title") if isinstance(job_description, dict) else str(job_description)},
        )
        return output

    def explain_decision(self, decision_context: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        rendered = DEFAULT_PROMPT_MANAGER.render(
            "explain_decision",
            decision_context=json.dumps(decision_context, ensure_ascii=False, indent=2),
            decision=json.dumps(decision, ensure_ascii=False, indent=2),
        )
        prompt_text = rendered.get("prompt") if isinstance(rendered, dict) else str(rendered)
        resp = self.chat.send_message(prompt_text)
        result = {
            "action": "explain_decision",
            "explanation": resp.get("content", ""),
            "provider": getattr(self.chat.provider, "__class__", None).__name__,
            "status": "ok",
        }
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="ai_assistant_explain_decision",
            resource_type="system",
            resource_id=None,
            metadata={"decision_context_preview": str(decision_context)[:160]},
        )
        return result

