from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.search import SearchRepository
from app.schemas.search import RecruiterSearchEntityType, RecruiterSearchResponse
from app.services.recruiter_search import SearchService

router = APIRouter(prefix="/search", tags=["search"])


def get_search_service(db: Session = Depends(get_db)) -> SearchService:
    return SearchService(
        SearchRepository(db),
        CompanyMemberRepository(db),
        BranchRepository(db),
    )


def _handle_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


def _parse_types(raw: str | None) -> set[RecruiterSearchEntityType] | None:
    if raw is None or not raw.strip():
        return None
    values: set[RecruiterSearchEntityType] = set()
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        try:
            values.add(RecruiterSearchEntityType(token))
        except ValueError as exc:
            raise ValueError("types must be candidate, job, and/or application") from exc
    return values or None


@router.get("", response_model=RecruiterSearchResponse)
@router.get("/", response_model=RecruiterSearchResponse, include_in_schema=False)
def recruiter_search(
    q: str = Query("", max_length=200),
    branch_id: UUID | None = Query(None),
    types: str | None = Query(None, description="Comma-separated: candidate,job,application"),
    offset: int = Query(0, ge=0, le=10_000),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> RecruiterSearchResponse:
    try:
        return service.search(
            current_user,
            q,
            branch_id=branch_id,
            types=_parse_types(types),
            offset=offset,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise
