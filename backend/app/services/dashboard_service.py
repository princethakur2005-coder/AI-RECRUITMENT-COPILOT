from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


class DashboardService:
    """Minimal dashboard service used by API endpoints and other services.

    This lightweight implementation returns zeroed/default metrics so the
    application can import and run without requiring full analytics logic.
    """

    def __init__(self, db: Any = None, notification_service: Any | None = None) -> None:
        self.db = db
        self.notification_service = notification_service

    def get_dashboard(self) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        return {
            "overview": {
                "total_candidates": 0,
                "total_jobs": 0,
                "interview_sessions": 0,
                "hired": 0,
                "generated_at": now,
            },
            "candidate_metrics": {"status_counts": {}, "total": 0, "recent_candidates": []},
            "job_metrics": {"status_counts": {}, "jobs_by_department": {}, "total": 0},
            "interview_metrics": {"interview_events": {}, "average_interview_duration_minutes": 0.0, "interview_sessions": 0},
            "hiring_metrics": {"hired": 0, "rejected": 0, "offers_in_progress": 0, "interviews_in_progress": 0, "screening_in_progress": 0, "new_candidates": 0, "total_candidates": 0, "hire_rate": 0.0},
            "recent_activity_summary": {"total_recent_activities": 0, "by_action": {}, "by_entity_type": {}, "items": []},
            "notification_summary": {"total": 0, "unread": 0, "read": 0, "high_priority": 0},
            "pipeline": {},
            "funnel": {},
            "job_statistics": {},
            "recent_activity": {},
            "generated_at": now,
        }

    def get_pipeline_widget(self) -> Dict[str, Any]:
        return {"stages": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    def get_funnel_widget(self) -> Dict[str, Any]:
        return {"buckets": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    def get_job_statistics_widget(self) -> Dict[str, Any]:
        return {"by_department": {}, "total_jobs": 0, "generated_at": datetime.utcnow().isoformat() + "Z"}

    def get_interview_metrics_widget(self) -> Dict[str, Any]:
        return {"interviews": {}, "average_duration_minutes": 0.0, "generated_at": datetime.utcnow().isoformat() + "Z"}

    def get_activity_widget(self) -> Dict[str, Any]:
        return {"items": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    def get_ai_activity_events(self, **kwargs: Any) -> Dict[str, Any]:
        return {"items": [], "total": 0, "page": kwargs.get("page", 1), "page_size": kwargs.get("page_size", 20)}

    def get_recent_activity_summary(self) -> Dict[str, Any]:
        return {"total_recent_activities": 0, "by_action": {}, "by_entity_type": {}, "items": []}

    def get_notification_summary(self) -> Dict[str, Any]:
        return {"total": 0, "unread": 0, "read": 0, "high_priority": 0}
