from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.user import UserRepository
from app.schemas.company_member import CompanyMemberCreate, CompanyMemberResponse
from app.services.company_member import CompanyMemberService

router = APIRouter(prefix="/companies/{company_id}/members", tags=["company-members"])


def get_company_member_service(db: Session = Depends(get_db)) -> CompanyMemberService:
    return CompanyMemberService(
        CompanyMemberRepository(db),
        CompanyRepository(db),
        UserRepository(db),
        BranchRepository(db),
    )


@router.post("", response_model=CompanyMemberResponse, status_code=status.HTTP_201_CREATED)
def add_company_member(
    company_id: UUID,
    payload: CompanyMemberCreate,
    current_user: User = Depends(get_current_user),
    service: CompanyMemberService = Depends(get_company_member_service),
) -> CompanyMemberResponse:
    try:
        member = service.add_member(current_user, company_id, payload)
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return member


@router.get("", response_model=list[CompanyMemberResponse])
def list_company_members(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CompanyMemberService = Depends(get_company_member_service),
) -> list[CompanyMemberResponse]:
    try:
        return service.list_members(current_user, company_id)
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
