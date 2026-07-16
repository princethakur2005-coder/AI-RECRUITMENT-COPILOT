from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.audit_service import audit_service


class CalendarProviderAdapter:
    """Abstract adapter interface for calendar providers (Google, Outlook).

    Concrete implementations should subclass and implement the methods.
    """

    provider_name = "base"

    def create_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()

    def update_event(self, event_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()

    def delete_event(self, event_id: str) -> None:
        raise NotImplementedError()

    def list_events(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        raise NotImplementedError()


class GoogleCalendarAdapter(CalendarProviderAdapter):
    provider_name = "google"

    def __init__(self, credentials: Optional[Dict[str, Any]] = None) -> None:
        self.credentials = credentials

    def create_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Google Calendar integration not implemented")

    def update_event(self, event_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Google Calendar integration not implemented")

    def delete_event(self, event_id: str) -> None:
        raise NotImplementedError("Google Calendar integration not implemented")

    def list_events(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        raise NotImplementedError("Google Calendar integration not implemented")


class OutlookCalendarAdapter(CalendarProviderAdapter):
    provider_name = "outlook"

    def __init__(self, credentials: Optional[Dict[str, Any]] = None) -> None:
        self.credentials = credentials

    def create_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Outlook integration not implemented")

    def update_event(self, event_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Outlook integration not implemented")

    def delete_event(self, event_id: str) -> None:
        raise NotImplementedError("Outlook integration not implemented")

    def list_events(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        raise NotImplementedError("Outlook integration not implemented")


class SchedulingStore:
    """File-backed store for scheduled interviews."""

    STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scheduled_interviews.json")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        if not os.path.exists(self.STORAGE_PATH):
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.STORAGE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def list_all(self) -> List[Dict[str, Any]]:
        data = self._load()
        return list(data.values())

    def get(self, interview_id: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        return data.get(interview_id)

    def save(self, interview: Dict[str, Any]) -> None:
        data = self._load()
        data[interview["id"]] = interview
        self._save(data)

    def delete(self, interview_id: str) -> None:
        data = self._load()
        if interview_id in data:
            del data[interview_id]
            self._save(data)


class SchedulingService:
    """Reusable scheduling service coordinating availability and calendar providers."""

    def __init__(self, provider_adapter: Optional[CalendarProviderAdapter] = None) -> None:
        self.adapter = provider_adapter
        self.store = SchedulingStore()

    def propose_slots(
        self,
        interviewer_availability: List[Tuple[datetime, datetime]],
        candidate_availability: List[Tuple[datetime, datetime]],
        duration_minutes: int = 30,
        max_slots: int = 5,
    ) -> List[Dict[str, Any]]:
        """Propose intersection slots between interviewer and candidate availability.

        Both availability lists are lists of (start, end) datetimes. Returns candidate slots.
        """
        slots: List[Dict[str, Any]] = []
        for i_start, i_end in interviewer_availability:
            for c_start, c_end in candidate_availability:
                start = max(i_start, c_start)
                end = min(i_end, c_end)
                current = start
                while current + timedelta(minutes=duration_minutes) <= end and len(slots) < max_slots:
                    slot = {"start": current.isoformat(), "end": (current + timedelta(minutes=duration_minutes)).isoformat()}
                    slots.append(slot)
                    current += timedelta(minutes=duration_minutes)
        return slots

    def _check_conflicts(self, participant_calendar_entries: List[Dict[str, Any]], start: datetime, end: datetime) -> bool:
        for ev in participant_calendar_entries:
            ev_start = datetime.fromisoformat(ev["start"]) if isinstance(ev["start"], str) else ev["start"]
            ev_end = datetime.fromisoformat(ev["end"]) if isinstance(ev["end"], str) else ev["end"]
            # overlap
            if not (end <= ev_start or start >= ev_end):
                return True
        return False

    def book_interview(
        self,
        candidate: Dict[str, Any],
        interviewers: List[Dict[str, Any]],
        start: datetime,
        duration_minutes: int = 30,
        location: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Book an interview if no conflicts exist. Returns scheduled interview entry.

        This method checks local store for conflicts and optionally delegates to calendar provider adapter.
        """
        end = start + timedelta(minutes=duration_minutes)

        # Check local conflicts for candidate and interviewers
        all_events = self.store.list_all()
        # Build participant calendars
        participant_calendars: Dict[str, List[Dict[str, Any]]] = {}
        for ev in all_events:
            for p in ev.get("participants", []):
                participant_calendars.setdefault(p, []).append({"start": ev["start"], "end": ev["end"]})

        cand_id = candidate.get("id") or candidate.get("email")
        if self._check_conflicts(participant_calendars.get(cand_id, []), start, end):
            raise ValueError("Candidate has a conflicting event")

        for intr in interviewers:
            intr_id = intr.get("id") or intr.get("email")
            if self._check_conflicts(participant_calendars.get(intr_id, []), start, end):
                raise ValueError(f"Interviewer {intr_id} has a conflicting event")

        interview_id = str(uuid.uuid4())
        interview = {
            "id": interview_id,
            "title": title or "Interview",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "participants": [candidate.get("id") or candidate.get("email")] + [intr.get("id") or intr.get("email") for intr in interviewers],
            "location": location,
            "metadata": metadata or {},
        }

        # Create event on external calendar if adapter present
        if self.adapter:
            # adapter.create_event may raise if not implemented
            try:
                external = self.adapter.create_event(interview)
                interview["external_event"] = {"provider": self.adapter.provider_name, "data": external}
            except NotImplementedError:
                # adapter not implemented; continue with local booking
                pass

        self.store.save(interview)
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="interview_scheduled",
            resource_type="candidate",
            resource_id=str(candidate.get("id") or candidate.get("email")),
            metadata={
                "interview_id": interview_id,
                "title": interview.get("title"),
                "start": interview.get("start"),
                "end": interview.get("end"),
                "participants": interview.get("participants"),
                "location": interview.get("location"),
            },
        )
        return interview

    def cancel_interview(self, interview_id: str) -> None:
        interview = self.store.get(interview_id)
        if not interview:
            raise KeyError("Interview not found")

        # delete external event
        external = interview.get("external_event")
        if external and self.adapter and external.get("provider") == self.adapter.provider_name:
            try:
                ev = external.get("data") or {}
                ev_id = ev.get("id")
                if ev_id:
                    self.adapter.delete_event(ev_id)
            except NotImplementedError:
                pass

        self.store.delete(interview_id)
        audit_service.log(
            actor_id="system",
            actor_type="system",
            action="interview_cancelled",
            resource_type="candidate",
            resource_id=str(interview.get("participants", [None])[0] or "unknown"),
            metadata={
                "interview_id": interview_id,
                "title": interview.get("title"),
                "start": interview.get("start"),
                "end": interview.get("end"),
                "location": interview.get("location"),
            },
        )

    def list_interviews(self, participant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self.store.list_all()
        if participant_id is None:
            return events
        return [e for e in events if participant_id in (e.get("participants") or [])]
