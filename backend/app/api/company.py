from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.company import CompanyRepository
from app.repositories.user import UserRepository
from app.schemas.company import CompanyCreate, CompanyResponse
from app.services.company import CompanyService

router = APIRouter(prefix="/companies", tags=["companies"])


def get_company_service(db: Session = Depends(get_db)) -> CompanyService:
    return CompanyService(CompanyRepository(db), UserRepository(db))


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    try:
        company = service.create_company(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return company
