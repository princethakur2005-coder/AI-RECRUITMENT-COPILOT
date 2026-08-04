from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company import CompanyRepository
from app.schemas.branch import BranchCreate, BranchResponse
from app.services.branch import BranchService

router = APIRouter(prefix="/companies/{company_id}/branches", tags=["branches"])


def get_branch_service(db: Session = Depends(get_db)) -> BranchService:
    return BranchService(BranchRepository(db), CompanyRepository(db))


@router.post("", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
def create_branch(
    company_id: UUID,
    payload: BranchCreate,
    current_user: User = Depends(get_current_user),
    service: BranchService = Depends(get_branch_service),
) -> BranchResponse:
    try:
        branch = service.create_branch(current_user, company_id, payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return branch


@router.get("", response_model=list[BranchResponse])
def list_branches(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    service: BranchService = Depends(get_branch_service),
) -> list[BranchResponse]:
    try:
        return service.list_branches(current_user, company_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
