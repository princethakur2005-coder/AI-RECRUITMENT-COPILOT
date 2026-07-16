from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.chat_service import ChatService


class EmailService:
    """Generate professional recruitment emails using the shared ChatService.

    Does not mutate global prompt templates; templates are maintained locally
    to the service for flexibility.
    """

    DEFAULT_TEMPLATES = {
        "reachout": (
            "Write a professional outreach email to {candidate_name} for the role of {job_title} at {company}."
            " Mention why they are a fit based on {highlights}. Include a clear call-to-action to schedule a call."
        ),
        "interview_invite": (
            "Write a polite interview invitation to {candidate_name} for the position {job_title} at {company}."
            " Provide date/time options, expected duration, and interview format."
        ),
        "follow_up": (
            "Write a concise follow-up email to {candidate_name} thanking them for their time and next steps."
        ),
        "rejection": (
            "Write a compassionate rejection email to {candidate_name} for the role {job_title} at {company}."
            " Offer brief feedback and encourage future opportunities."
        ),
    }

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)

    def generate_email(
        self,
        template: str,
        candidate_name: str,
        job_title: str,
        company: str,
        highlights: Optional[str] = None,
        tone: str = "professional",
        max_words: int = 200,
    ) -> Dict[str, Any]:
        tpl = self.DEFAULT_TEMPLATES.get(template)
        if tpl is None:
            raise KeyError(f"Unknown email template: {template}")

        prompt = tpl.format(candidate_name=candidate_name, job_title=job_title, company=company, highlights=highlights or "relevant experience")
        prompt = (
            f"{prompt}\n\nTone: {tone}. Keep the email under {max_words} words.\n"
            "Return only the email body text without commentary."
        )

        resp = self.chat.send_message(prompt)
        return {"email": resp.get("content", ""), "raw": resp}

    # convenience wrappers
    def outreach(self, **kwargs: Any) -> Dict[str, Any]:
        return self.generate_email(template="reachout", **kwargs)

    def invite(self, **kwargs: Any) -> Dict[str, Any]:
        return self.generate_email(template="interview_invite", **kwargs)

    def follow_up(self, **kwargs: Any) -> Dict[str, Any]:
        return self.generate_email(template="follow_up", **kwargs)

    def rejection(self, **kwargs: Any) -> Dict[str, Any]:
        return self.generate_email(template="rejection", **kwargs)
