from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.candidate import router as candidate_router
from app.api.dashboard import router as dashboard_router
from app.api.job import router as job_router
from app.api.note import router as note_router
from app.api.offer import router as offer_router
from app.api.search import router as search_router
from app.api.user import router as user_router
from app.api.workspace import router as workspace_router

__all__ = [
    "assistant_router",
    "auth_router",
    "candidate_router",
    "dashboard_router",
    "job_router",
    "note_router",
    "offer_router",
    "search_router",
    "user_router",
    "workspace_router",
]
