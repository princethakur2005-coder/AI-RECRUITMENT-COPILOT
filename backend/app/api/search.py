from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


def get_search_service(db: Session = Depends(get_db)) -> SearchService:
    return SearchService(db=db)


@router.get("/")
def global_search(
    scope: str = Query("candidates", pattern="^(candidates|jobs|interviews|resumes)$"),
    query: str = Query(..., min_length=1),
    sort_by: str | None = Query(None),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> dict:
    result = service.search(
        scope=scope,
        query=query,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
