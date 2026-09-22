from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.application_status import ApplicationStatus, PIPELINE_STATUSES
from app.models.application import Application
from app.models.job import Job
from app.models.interview import Interview


class DashboardService:
    """Live Recruiter Dashboard Aggregation and Stack Ranking Service."""

    def __init__(self, db: Session | Any = None, notification_service: Any | None = None) -> None:
        self.db = db
        self.notification_service = notification_service

    def get_dashboard_summary(
        self,
        company_id: UUID,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Return live Tenant-isolated KPIs, pipeline stage counts, and top ranked candidates."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.db is None:
            return {
                "kpis":{
                    "total_candidates": 0,
                    "active_jobs": 0,
                    "interviews_completed": 0,
                    "pending_decisions": 0,
                },
                "pipeline_overview": {status.value: 0 for status in PIPELINE_STATUSES},
                "top_candidates": [],
                "generated_at": now_iso,
            }

        # 1. KPIs: Live PostgreSQL Database Aggregates
        # Total Unique Candidates for this Company
        total_candidates = (
            self.db.scalar(
                select(func.count(func.distinct(Application.candidate_id))).where(
                    Application.company_id == company_id
                )
            )
            or 0
        )

        # Active Jobs
        active_jobs = (
            self.db.scalar(
                select(func.count(Job.id)).where(
                    Job.company_id == company_id,
                    Job.is_active.is_(True),
                )
            )
            or 0
        )

        # Interviews Completed
        interviews_completed = (
            self.db.scalar(
                select(func.count(Interview.id)).where(
                    Interview.company_id == company_id,
                    Interview.status == "completed",
                )
            )
            or 0
        )

        # Candidates ready for offer/decision (Pending Decisions)
        pending_decisions_query = select(func.count(Application.id)).where(
            Application.company_id == company_id,
            Application.status.in_([
                ApplicationStatus.INTERVIEW_COMPLETED.value,
                ApplicationStatus.DECISION_READY.value,
                ApplicationStatus.SHORTLISTED.value,
            ]),
        )
        pending_decisions = self.db.scalar(pending_decisions_query) or 0

        # 2. Pipeline Overview: Counts per status stage
        status_rows = self.db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.company_id == company_id)
            .group_by(Application.status)
        ).all()
        pipeline_map = {status.value: 0 for status in PIPELINE_STATUSES}
        for status_val, cnt in status_rows:
            pipeline_map[status_val] = int(cnt)


        # 3. Top Candidates Ranked by Composite Score
        applications = (
            self.db.query(Application)
            .options(
                joinedload(Application.candidate),
                joinedload(Application.job),
                joinedload(Application.ai_analysis),
            )
            .filter(Application.company_id == company_id)
            .all()
        )

        ranked_entries: list[tuple[Application, float, str, str]] = []
        for app in applications:
            dec = app.hiring_decision_json or {}
            if app.composite_score is not None:
                score = float(app.composite_score)
                rec = dec.get("recommendation") or "hire"
                ranked_entries.append((app, score, rec, "composite"))
            elif app.ai_analysis is not None:
                score = float(app.ai_analysis.overall_score)
                rec = app.ai_analysis.recommendation or "review"
                ranked_entries.append((app, score, rec, "resume_analysis"))
            elif any(s is not None for s in (app.fit_score, app.assessment_score, app.interview_score)):
                scores_present = [float(s) for s in (app.fit_score, app.assessment_score, app.interview_score) if s is not None]
                score = round(sum(scores_present) / len(scores_present), 1)
                rec = "hire" if score >= 70.0 else ("review" if score >= 55.0 else "reject")
                ranked_entries.append((app, score, rec, "stages"))

        ranked_entries.sort(key=lambda e: (-e[1], e[0].applied_at))
        top_slice = ranked_entries[:max(1, limit)]


        top_candidates = []
        for index, (app, score, rec, _) in enumerate(top_slice, start=1):
            cand_name = app.candidate.full_name if app.candidate else None
            job_title = app.job.title if app.job else None
            top_candidates.append({
                "rank": index,
                "application_id": str(app.id),
                "candidate_id": str(app.candidate_id),
                "candidate_name": cand_name,
                "job_id": str(app.job_id),
                "job_title": job_title,
                "composite_score": score,
                "overall_rank_score": score,
                "recommendation": rec,
                "status": app.status,
            })


        overview_data = {
            "total_candidates": int(total_candidates),
            "total_jobs": int(active_jobs),
            "interview_sessions": int(interviews_completed),
            "hired": pipeline_map.get("hired", 0),
            "generated_at": now_iso,
        }

        return {
            "kpis": {
                "total_candidates": int(total_candidates),
                "active_jobs": int(active_jobs),
                "interviews_completed": int(interviews_completed),
                "pending_decisions": int(pending_decisions),
            },
            "pipeline_overview": pipeline_map,
            "pipeline_stages": pipeline_map,
            "funnel": pipeline_map,
            "stages": pipeline_map,
            "overview": overview_data,
            "candidate_metrics": {"status_counts": pipeline_map, "total": int(total_candidates)},
            "job_metrics": {"status_counts": {}, "jobs_by_department": {}, "total": int(active_jobs)},
            "interview_metrics": {"interview_events": {}, "average_interview_duration_minutes": 45.0, "interview_sessions": int(interviews_completed)},
            "hiring_metrics": {
                "hired": pipeline_map.get("hired", 0),
                "rejected": pipeline_map.get("rejected", 0),
                "offers_in_progress": pipeline_map.get("offered", 0),
                "interviews_in_progress": pipeline_map.get("interview", 0),
                "screening_in_progress": pipeline_map.get("screening", 0),
                "new_candidates": pipeline_map.get("applied", 0),
                "total_candidates": int(total_candidates),
                "hire_rate": round(pipeline_map.get("hired", 0) / max(total_candidates, 1) * 100, 1),
            },
            "top_candidates": top_candidates,
            "generated_at": now_iso,
        }


    def get_dashboard(self, company_id: UUID | None = None) -> Dict[str, Any]:
        if company_id is not None and self.db is not None:
            summary = self.get_dashboard_summary(company_id)
            kpis = summary["kpis"]
            return {
                "overview": summary["overview"],
                "candidate_metrics": summary["candidate_metrics"],
                "job_metrics": summary["job_metrics"],
                "interview_metrics": summary["interview_metrics"],
                "hiring_metrics": summary["hiring_metrics"],
                "recent_activity_summary": {"total_recent_activities": 0, "by_action": {}, "by_entity_type": {}, "items": []},
                "notification_summary": {"total": 0, "unread": 0, "read": 0, "high_priority": 0},
                "pipeline": summary["pipeline_overview"],
                "funnel": summary["pipeline_overview"],
                "job_statistics": {},
                "recent_activity": {},
                "generated_at": summary["generated_at"],
            }

        now = datetime.now(timezone.utc).isoformat()
        return {
            "overview": {"total_candidates": 0, "total_jobs": 0, "interview_sessions": 0, "hired": 0, "generated_at": now},
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

    def get_pipeline_widget(self, company_id: UUID | None = None) -> Dict[str, Any]:
        stages: dict[str, int] = {}
        if company_id and self.db:
            summary = self.get_dashboard_summary(company_id)
            stages = summary.get("pipeline_overview", {})
        return {
            "pipeline_stages": stages,
            "total_in_pipeline": sum(stages.values()) if stages else 0,
            "stages": stages,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_funnel_widget(self, company_id: UUID | None = None) -> Dict[str, Any]:
        stages: dict[str, int] = {}
        if company_id and self.db:
            summary = self.get_dashboard_summary(company_id)
            stages = summary.get("pipeline_overview", {})
        return {
            "funnel": stages,
            "stages": stages,
            "counts": stages,
            "total": sum(stages.values()) if stages else 0,
            "buckets": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_job_statistics_widget(self, company_id: UUID | None = None) -> Dict[str, Any]:
        by_dept: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_jobs = 0
        if company_id and self.db:
            jobs = self.db.query(Job).filter(Job.company_id == company_id).all()
            total_jobs = len(jobs)
            for j in jobs:
                dept = j.department or "General"
                by_dept[dept] = by_dept.get(dept, 0) + 1
                status_counts[j.status] = status_counts.get(j.status, 0) + 1
        return {
            "jobs_by_department": by_dept,
            "job_status_counts": status_counts,
            "total_jobs": total_jobs,
            "by_department": by_dept,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_interview_metrics_widget(self, company_id: UUID | None = None) -> Dict[str, Any]:
        count = 0
        if company_id and self.db:
            count = self.db.query(Interview).filter(Interview.company_id == company_id).count()
        return {
            "interview_events": {"scheduled": count},
            "average_interview_duration_minutes": 45.0,
            "interview_sessions": count,
            "interviews": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_activity_widget(self) -> Dict[str, Any]:
        return {"items": [], "generated_at": datetime.now(timezone.utc).isoformat()}

    def get_ai_activity_events(self, **kwargs: Any) -> Dict[str, Any]:
        return {"items": [], "total": 0, "page": kwargs.get("page", 1), "page_size": kwargs.get("page_size", 20)}

    def get_recent_activity_summary(self) -> Dict[str, Any]:
        return {"total_recent_activities": 0, "by_action": {}, "by_entity_type": {}, "items": []}


    def get_notification_summary(self) -> Dict[str, Any]:
        return {"total": 0, "unread": 0, "read": 0, "high_priority": 0}
