from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.candidate import Candidate
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateCreate, CandidateResponse, CandidateUpdate
from app.services.audit_service import audit_service
from app.services.candidate import CandidateService

router = APIRouter(prefix="/candidates", tags=["candidates"])


def get_candidate_service(db: Session = Depends(get_db)) -> CandidateService:
    repository = CandidateRepository(db)
    return CandidateService(repository)


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    service: CandidateService = Depends(get_candidate_service),
) -> Candidate:
    candidate = Candidate(**payload.model_dump())
    return service.create_candidate(candidate)


@router.get("", response_model=list[CandidateResponse])
def list_candidates(
    service: CandidateService = Depends(get_candidate_service),
) -> list[Candidate]:
    return service.get_all()


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: str,
    service: CandidateService = Depends(get_candidate_service),
) -> Candidate:
    candidate = service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return candidate


@router.get("/{candidate_id}/timeline")
def get_candidate_timeline(
    candidate_id: str,
    limit: int = Query(20, ge=1, le=100),
    service: CandidateService = Depends(get_candidate_service),
) -> list[dict]:
    candidate = service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return audit_service.get_candidate_timeline(candidate_id=candidate_id, limit=limit)


@router.put("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    service: CandidateService = Depends(get_candidate_service),
) -> Candidate:
    candidate = service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    update_data = payload.model_dump(exclude_unset=True)
    return service.update(candidate, update_data)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: str,
    service: CandidateService = Depends(get_candidate_service),
) -> None:
    candidate = service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    service.delete(candidate)
