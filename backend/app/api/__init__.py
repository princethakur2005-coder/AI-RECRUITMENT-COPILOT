from app.api.application import router as application_router
from app.api.audit import router as audit_router
from app.api.public_apply import router as public_apply_router
from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.branch import router as branch_router
from app.api.candidate import router as candidate_router
from app.api.candidate_portal import router as candidate_portal_router
from app.api.company import router as company_router
from app.api.company_member import router as company_member_router
from app.api.dashboard import router as dashboard_router
from app.api.job import router as job_router
from app.api.note import router as note_router
from app.api.offer import router as offer_router
from app.api.search import router as search_router
from app.api.user import router as user_router
from app.api.webhook import router as webhook_router
from app.api.calendar import router as calendar_router
from app.api.workspace import router as workspace_router

__all__ = [
    "application_router",
    "assistant_router",
    "audit_router",
    "auth_router",
    "branch_router",
    "calendar_router",
    "candidate_router",
    "candidate_portal_router",
    "company_router",
    "company_member_router",
    "dashboard_router",
    "job_router",
    "note_router",
    "offer_router",
    "public_apply_router",
    "search_router",
    "user_router",
    "webhook_router",
    "workspace_router",
]
