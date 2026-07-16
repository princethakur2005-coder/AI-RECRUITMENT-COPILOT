from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.services.chat_service import ChatService


class FeedbackAnalysisService:
    """Analyze interview feedback and produce structured insights.

    Uses `ChatService` (Gemini) to perform analysis and falls back to simple
    heuristics when a structured response is not returned.
    """

    POSITIVE = ["excellent", "strong", "good", "outstanding", "confident", "skilled", "impressive"]
    NEGATIVE = ["poor", "weak", "inexperienced", "concern", "lack", "needs improvement"]

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)

    def analyze_feedback(self, feedback_items: List[str], candidate_name: str | None = None) -> Dict[str, Any]:
        """Return structured feedback: strengths, weaknesses, recommended_actions, score (0..1)."""
        combined = "\n---\n".join(feedback_items)

        prompt = (
            f"You are an expert hiring analyst. Analyze the following interview feedback for {candidate_name or 'the candidate'}:\n\n{combined}\n\n"
            "Return a single JSON object with keys: strengths (array), weaknesses (array), recommended_actions (array), overall_recommendation (hire|hold|no_hire), score (0..1)."
        )

        resp = self.chat.send_message(prompt)
        content = resp.get("content", "") or ""

        result = {"strengths": [], "weaknesses": [], "recommended_actions": [], "overall_recommendation": "hold", "score": 0.0, "raw": resp}

        if content.strip():
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    # map keys
                    for k in ("strengths", "weaknesses", "recommended_actions", "overall_recommendation", "score"):
                        if k in parsed:
                            result[k] = parsed[k]
                    return result
            except Exception:
                pass

        # Heuristic fallback
        text = combined.lower()
        pos = sum(1 for w in self.POSITIVE if re.search(r"\b" + re.escape(w) + r"\b", text))
        neg = sum(1 for w in self.NEGATIVE if re.search(r"\b" + re.escape(w) + r"\b", text))

        strengths = []
        weaknesses = []
        for line in feedback_items:
            lowered = line.lower()
            if any(p in lowered for p in self.POSITIVE):
                strengths.append(line.strip())
            if any(n in lowered for n in self.NEGATIVE):
                weaknesses.append(line.strip())

        # Recommended actions derived from weaknesses
        actions = []
        if weaknesses:
            actions.append("Schedule a technical follow-up focusing on areas of weakness")
        else:
            actions.append("Proceed to next stage or consider offer if strong cultural fit")

        score = max(0.0, min(1.0, (pos - neg) / max(1, pos + neg))) if (pos + neg) > 0 else 0.5

        result.update({"strengths": strengths, "weaknesses": weaknesses, "recommended_actions": actions, "score": round(score, 2)})
        return result
