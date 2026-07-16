from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from app.services.chat_service import ChatService


class InterviewType(str, Enum):
    MCQ = "mcq"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    CODING = "coding"


class InteractionModality(str, Enum):
    TEXT = "text"
    SPEECH = "speech"
    VIDEO = "video"


@dataclass
class InterviewQuestion:
    id: str
    interview_type: InterviewType
    prompt: str
    difficulty: str = "medium"
    options: List[str] = field(default_factory=list)
    expected_competencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InterviewAnswer:
    question_id: str
    answer_text: str
    submitted_at: str
    score: Optional[float] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InterviewTemplate:
    id: str
    name: str
    role: str
    version: str
    enabled: bool
    interview_types: List[InterviewType]
    opening_questions: List[InterviewQuestion]
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SessionProgress:
    total_questions: int = 0
    asked_questions: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    cumulative_score: float = 0.0
    avg_confidence: float = 0.0


@dataclass
class InterviewSession:
    id: str
    template_id: str
    candidate_id: str
    modality: InteractionModality
    started_at: str
    status: str = "active"
    current_question: Optional[InterviewQuestion] = None
    asked_questions: List[InterviewQuestion] = field(default_factory=list)
    answers: List[InterviewAnswer] = field(default_factory=list)
    progress: SessionProgress = field(default_factory=SessionProgress)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TemplateRepository(Protocol):
    def save(self, template: InterviewTemplate) -> None:
        ...

    def get(self, template_id: str) -> Optional[InterviewTemplate]:
        ...

    def list_enabled(self) -> List[InterviewTemplate]:
        ...


class SessionRepository(Protocol):
    def save(self, session: InterviewSession) -> None:
        ...

    def get(self, session_id: str) -> Optional[InterviewSession]:
        ...


class InteractionChannelAdapter(Protocol):
    """Channel abstraction for text today, speech/video tomorrow."""

    modality: InteractionModality

    def collect_response(self, session: InterviewSession) -> str:
        ...

    def present_question(self, question: InterviewQuestion, session: InterviewSession) -> None:
        ...


class SpeechToTextAdapter(Protocol):
    """Future extension point for audio transcription."""

    def transcribe(self, audio_uri: str) -> str:
        ...


class VideoInterviewAdapter(Protocol):
    """Future extension point for video signals/metadata extraction."""

    def analyze(self, video_uri: str) -> Dict[str, Any]:
        ...


class InMemoryTemplateRepository(TemplateRepository):
    def __init__(self) -> None:
        self._templates: Dict[str, InterviewTemplate] = {}

    def save(self, template: InterviewTemplate) -> None:
        template.updated_at = datetime.now(timezone.utc).isoformat()
        self._templates[template.id] = template

    def get(self, template_id: str) -> Optional[InterviewTemplate]:
        return self._templates.get(template_id)

    def list_enabled(self) -> List[InterviewTemplate]:
        return [item for item in self._templates.values() if item.enabled]


class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._sessions: Dict[str, InterviewSession] = {}

    def save(self, session: InterviewSession) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> Optional[InterviewSession]:
        return self._sessions.get(session_id)


class AnswerEvaluationEngine:
    """Lightweight answer evaluator with deterministic enterprise fallback."""

    POSITIVE_TOKENS = {
        "designed",
        "implemented",
        "optimized",
        "improved",
        "scalable",
        "tradeoff",
        "testing",
        "ownership",
        "collaborated",
        "measured",
    }

    def evaluate(self, question: InterviewQuestion, answer_text: str) -> InterviewAnswer:
        normalized = (answer_text or "").strip()
        score = self._heuristic_score(question, normalized)
        confidence = self._heuristic_confidence(normalized)
        rationale = self._rationale_for(score)

        return InterviewAnswer(
            question_id=question.id,
            answer_text=normalized,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            score=score,
            confidence=confidence,
            rationale=rationale,
        )

    def _heuristic_score(self, question: InterviewQuestion, answer_text: str) -> float:
        if not answer_text:
            return 0.0

        token_count = len(re.findall(r"[a-zA-Z0-9_+#.-]+", answer_text.lower()))
        richness = min(1.0, token_count / 80.0)

        quality_hits = 0
        lowered = answer_text.lower()
        for token in self.POSITIVE_TOKENS:
            if token in lowered:
                quality_hits += 1
        quality = min(1.0, quality_hits / 6.0)

        if question.interview_type == InterviewType.MCQ:
            # For MCQ, fallback score is based on concise answer quality.
            return round(0.6 * quality + 0.4 * min(1.0, token_count / 20.0), 2)

        return round(0.45 * richness + 0.55 * quality, 2)

    def _heuristic_confidence(self, answer_text: str) -> float:
        if not answer_text:
            return 0.2
        tokens = len(re.findall(r"[a-zA-Z0-9_+#.-]+", answer_text))
        return round(min(1.0, 0.25 + tokens / 120.0), 2)

    def _rationale_for(self, score: float) -> str:
        if score >= 0.8:
            return "Strong, structured response with clear reasoning."
        if score >= 0.55:
            return "Reasonable response with partial depth and coverage."
        if score >= 0.3:
            return "Limited depth; follow-up probing recommended."
        return "Insufficient evidence in response; major probing required."


class AdaptiveFlowStrategy(Protocol):
    def choose_next_type(self, template: InterviewTemplate, session: InterviewSession) -> InterviewType:
        ...

    def choose_next_difficulty(self, session: InterviewSession) -> str:
        ...


class DefaultAdaptiveFlowStrategy:
    """Adaptive strategy based on answer quality and type coverage."""

    DIFFICULTY_ORDER = ["easy", "medium", "hard"]

    def choose_next_type(self, template: InterviewTemplate, session: InterviewSession) -> InterviewType:
        configured = template.interview_types or [InterviewType.TECHNICAL]
        counts = session.progress.by_type

        least_count = None
        next_type = configured[0]
        for interview_type in configured:
            count = counts.get(interview_type.value, 0)
            if least_count is None or count < least_count:
                least_count = count
                next_type = interview_type

        if session.answers:
            last_answer = session.answers[-1]
            if (last_answer.score or 0.0) < 0.35 and InterviewType.BEHAVIORAL in configured:
                return InterviewType.BEHAVIORAL

        return next_type

    def choose_next_difficulty(self, session: InterviewSession) -> str:
        avg_score = 0.0
        if session.answers:
            valid = [ans.score for ans in session.answers if ans.score is not None]
            if valid:
                avg_score = sum(valid) / len(valid)

        if avg_score >= 0.75:
            return "hard"
        if avg_score >= 0.4:
            return "medium"
        return "easy"


class FollowUpQuestionGenerator:
    """AI follow-up generation with robust deterministic fallback."""

    def __init__(self, provider: Any | None = None) -> None:
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)

    def generate(
        self,
        previous_question: InterviewQuestion,
        previous_answer: InterviewAnswer,
        next_type: InterviewType,
        difficulty: str,
    ) -> InterviewQuestion:
        prompt = (
            "You are an enterprise interview engine. Generate exactly one follow-up interview question in JSON. "
            "Return keys: prompt, options (array for mcq else []), competencies (array). "
            f"Previous question type: {previous_question.interview_type.value}. "
            f"Previous question: {previous_question.prompt}\n"
            f"Candidate answer: {previous_answer.answer_text}\n"
            f"Detected score: {previous_answer.score}, confidence: {previous_answer.confidence}. "
            f"Target next type: {next_type.value}, difficulty: {difficulty}."
        )

        ai = self.chat.send_message(prompt)
        content = ai.get("content", "") or ""

        parsed_prompt = ""
        parsed_options: List[str] = []
        competencies: List[str] = []

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                parsed_prompt = str(parsed.get("prompt") or "").strip()
                raw_options = parsed.get("options") or []
                if isinstance(raw_options, list):
                    parsed_options = [str(opt).strip() for opt in raw_options if str(opt).strip()]
                raw_comp = parsed.get("competencies") or []
                if isinstance(raw_comp, list):
                    competencies = [str(c).strip() for c in raw_comp if str(c).strip()]
        except Exception:
            pass

        if not parsed_prompt:
            parsed_prompt = self._fallback_prompt(previous_question, previous_answer, next_type)

        if next_type != InterviewType.MCQ:
            parsed_options = []
        elif not parsed_options:
            parsed_options = ["Option A", "Option B", "Option C", "Option D"]

        return InterviewQuestion(
            id=str(uuid.uuid4()),
            interview_type=next_type,
            prompt=parsed_prompt,
            difficulty=difficulty,
            options=parsed_options,
            expected_competencies=competencies,
            metadata={"source": "ai_follow_up"},
        )

    def _fallback_prompt(
        self,
        previous_question: InterviewQuestion,
        previous_answer: InterviewAnswer,
        next_type: InterviewType,
    ) -> str:
        if next_type == InterviewType.BEHAVIORAL:
            return "Describe a situation where your first approach failed. How did you adapt and what changed in outcome?"
        if next_type == InterviewType.CODING:
            return "Write pseudo-code for a solution, explain time/space complexity, and discuss one optimization trade-off."
        if next_type == InterviewType.MCQ:
            return "Which option best describes the safest production rollout strategy for a high-risk change?"
        return "Explain your previous approach in more depth and justify the technical trade-offs you made."


class AIInterviewEngine:
    """Foundation engine for template-based, adaptive AI interviews.

    Enterprise-focused design:
    - Template-driven interview creation
    - Adaptive flow strategy abstraction
    - Reusable answer evaluator and follow-up generator
    - Channel/modality extension points for speech/video support
    """

    def __init__(
        self,
        template_repository: TemplateRepository,
        session_repository: SessionRepository,
        flow_strategy: Optional[AdaptiveFlowStrategy] = None,
        follow_up_generator: Optional[FollowUpQuestionGenerator] = None,
        evaluator: Optional[AnswerEvaluationEngine] = None,
    ) -> None:
        self.template_repository = template_repository
        self.session_repository = session_repository
        self.flow_strategy = flow_strategy or DefaultAdaptiveFlowStrategy()
        self.follow_up_generator = follow_up_generator or FollowUpQuestionGenerator()
        self.evaluator = evaluator or AnswerEvaluationEngine()

    def register_template(self, template: InterviewTemplate) -> None:
        if not template.id:
            raise ValueError("template.id is required")
        if not template.name.strip():
            raise ValueError("template.name is required")
        if not template.interview_types:
            raise ValueError("template.interview_types must not be empty")
        self.template_repository.save(template)

    def start_session(
        self,
        template_id: str,
        candidate_id: str,
        modality: InteractionModality = InteractionModality.TEXT,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InterviewSession:
        template = self.template_repository.get(template_id)
        if not template or not template.enabled:
            raise ValueError("Template is not available")

        session = InterviewSession(
            id=str(uuid.uuid4()),
            template_id=template_id,
            candidate_id=candidate_id,
            modality=modality,
            started_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        opening = self._initial_question(template)
        session.current_question = opening
        session.asked_questions.append(opening)
        session.progress.total_questions = int(template.constraints.get("max_questions", 10))
        session.progress.asked_questions = 1
        session.progress.by_type[opening.interview_type.value] = 1

        self.session_repository.save(session)
        return session

    def submit_answer(self, session_id: str, answer_text: str) -> Dict[str, Any]:
        session = self.session_repository.get(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.status != "active":
            raise ValueError("Session is not active")
        if not session.current_question:
            raise ValueError("No active question in session")

        evaluated = self.evaluator.evaluate(session.current_question, answer_text)
        session.answers.append(evaluated)
        self._refresh_progress(session)

        template = self.template_repository.get(session.template_id)
        if not template:
            raise ValueError("Session template missing")

        if self._is_complete(session, template):
            session.status = "completed"
            session.current_question = None
            self.session_repository.save(session)
            return {
                "session": session,
                "completed": True,
                "next_question": None,
                "latest_answer": evaluated,
            }

        next_type = self.flow_strategy.choose_next_type(template, session)
        next_difficulty = self.flow_strategy.choose_next_difficulty(session)
        next_question = self.follow_up_generator.generate(
            previous_question=session.asked_questions[-1],
            previous_answer=evaluated,
            next_type=next_type,
            difficulty=next_difficulty,
        )

        session.current_question = next_question
        session.asked_questions.append(next_question)
        session.progress.asked_questions += 1
        session.progress.by_type[next_question.interview_type.value] = (
            session.progress.by_type.get(next_question.interview_type.value, 0) + 1
        )

        self.session_repository.save(session)
        return {
            "session": session,
            "completed": False,
            "next_question": next_question,
            "latest_answer": evaluated,
        }

    def _initial_question(self, template: InterviewTemplate) -> InterviewQuestion:
        if template.opening_questions:
            first = template.opening_questions[0]
            return InterviewQuestion(
                id=first.id or str(uuid.uuid4()),
                interview_type=first.interview_type,
                prompt=first.prompt,
                difficulty=first.difficulty or "medium",
                options=list(first.options),
                expected_competencies=list(first.expected_competencies),
                metadata=dict(first.metadata),
            )

        initial_type = template.interview_types[0]
        return InterviewQuestion(
            id=str(uuid.uuid4()),
            interview_type=initial_type,
            prompt=self._default_opening_prompt(initial_type),
            difficulty="medium",
            options=["Option A", "Option B", "Option C", "Option D"] if initial_type == InterviewType.MCQ else [],
            expected_competencies=[],
            metadata={"source": "default_opening"},
        )

    def _default_opening_prompt(self, interview_type: InterviewType) -> str:
        if interview_type == InterviewType.MCQ:
            return "Which principle most reduces deployment risk in distributed systems? Choose one and justify briefly."
        if interview_type == InterviewType.BEHAVIORAL:
            return "Tell me about a time you disagreed with your team on a technical decision."
        if interview_type == InterviewType.CODING:
            return "Implement a function to detect duplicates in near-linear time. Explain complexity."
        return "Design a resilient service for high-throughput event processing and explain your trade-offs."

    def _is_complete(self, session: InterviewSession, template: InterviewTemplate) -> bool:
        max_questions = int(template.constraints.get("max_questions", 10))
        min_questions = int(template.constraints.get("min_questions", 4))

        if session.progress.asked_questions >= max_questions:
            return True

        if session.progress.asked_questions < min_questions:
            return False

        # Completion when coverage target met and confidence is stable.
        required_types = set(item.value for item in template.interview_types)
        covered_types = set(k for k, v in session.progress.by_type.items() if v > 0)
        if not required_types.issubset(covered_types):
            return False

        return session.progress.avg_confidence >= float(template.constraints.get("completion_confidence", 0.65))

    def _refresh_progress(self, session: InterviewSession) -> None:
        scored = [item.score for item in session.answers if item.score is not None]
        confidences = [item.confidence for item in session.answers if item.confidence is not None]

        if scored:
            session.progress.cumulative_score = round(sum(scored) / len(scored), 2)
        if confidences:
            session.progress.avg_confidence = round(sum(confidences) / len(confidences), 2)
