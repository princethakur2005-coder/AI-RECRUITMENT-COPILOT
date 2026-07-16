from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.job import Job
from app.services.audit_service import audit_service
from app.services.chat_service import ChatService
from app.services.prompt_manager import DEFAULT_PROMPT_MANAGER
from app.utils.search_sort import QueryParams, SearchSortPaginator


class SearchService:
    """Global search engine supporting structured and semantic search."""

    def __init__(self, db: Session, provider: Any | None = None) -> None:
        self.db = db
        provider_name = getattr(provider, "provider_name", "gemini") if provider else "gemini"
        self.chat = ChatService(provider=provider, provider_name=provider_name)

    def _semantic_query(self, query: str, limit: int = 10) -> Dict[str, Any]:
        prompt = (
            f"You are a recruitment search assistant. Given the query: '{query}', "
            "identify relevant candidate, job, interview, and resume search facets. "
            "Return JSON with keys: candidate_terms, job_terms, interview_terms, resume_terms." 
        )
        resp = self.chat.send_message(prompt)
        content = resp.get("content", "") or ""
        try:
            parsed = json.loads(content)
            return {
                "candidate_terms": parsed.get("candidate_terms") or [],
                "job_terms": parsed.get("job_terms") or [],
                "interview_terms": parsed.get("interview_terms") or [],
                "resume_terms": parsed.get("resume_terms") or [],
            }
        except Exception:
            return {
                "candidate_terms": [query],
                "job_terms": [query],
                "interview_terms": [query],
                "resume_terms": [query],
            }

    def _candidate_search(self, query: str, params: QueryParams) -> Dict[str, Any]:
        candidate_terms = self._semantic_query(query).get("candidate_terms", [query])
        clauses = [Candidate.full_name.ilike(f"%{term}%") for term in candidate_terms]
        clauses += [Candidate.email.ilike(f"%{term}%") for term in candidate_terms]
        clauses += [Candidate.current_title.ilike(f"%{term}%") for term in candidate_terms]

        statement = select(Candidate).where(or_(*clauses))
        results = list(self.db.scalars(statement).all())
        return SearchSortPaginator.apply(results, params)

    def _job_search(self, query: str, params: QueryParams) -> Dict[str, Any]:
        job_terms = self._semantic_query(query).get("job_terms", [query])
        clauses = [Job.title.ilike(f"%{term}%") for term in job_terms]
        clauses += [Job.description.ilike(f"%{term}%") for term in job_terms]
        clauses += [Job.department.ilike(f"%{term}%") for term in job_terms]

        statement = select(Job).where(or_(*clauses))
        results = list(self.db.scalars(statement).all())
        return SearchSortPaginator.apply(results, params)

    def _interview_search(self, query: str, params: QueryParams) -> Dict[str, Any]:
        events = []
        for ev in audit_service.store.iter_events():
            if ev.get("action") and query.lower() in ev.get("action", "").lower():
                events.append(ev)
            elif ev.get("metadata") and query.lower() in str(ev.get("metadata", {})).lower():
                events.append(ev)
        return SearchSortPaginator.apply(events, params)

    def _resume_search(self, query: str, params: QueryParams) -> Dict[str, Any]:
        # Use candidate summary and skills fields as resume proxies.
        terms = self._semantic_query(query).get("resume_terms", [query])
        clauses = [Candidate.skills.ilike(f"%{term}%") for term in terms]
        clauses += [Candidate.summary.ilike(f"%{term}%") for term in terms]
        clauses += [Candidate.resume_path.ilike(f"%{term}%") for term in terms]

        statement = select(Candidate).where(or_(*clauses))
        results = list(self.db.scalars(statement).all())
        return SearchSortPaginator.apply(results, params)

    def search(
        self,
        scope: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        params = QueryParams(filters=filters, sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size)
        scope = scope.lower()

        if scope == "candidates":
            return self._candidate_search(query, params)
        if scope == "jobs":
            return self._job_search(query, params)
        if scope == "interviews":
            return self._interview_search(query, params)
        if scope == "resumes":
            return self._resume_search(query, params)

        return {
            "error": "Unsupported search scope. Use candidates, jobs, interviews, or resumes.",
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "pages": 0,
        }
