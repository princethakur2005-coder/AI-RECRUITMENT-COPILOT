from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.offer import Offer
from app.models.user import User
from app.repositories.offer import OfferRepository
from app.services.candidate import CandidateService
from app.services.offer_service import OfferService
from app.repositories.candidate import CandidateRepository
from app.schemas.offer import OfferCreate, OfferResponse, OfferUpdate

router = APIRouter(prefix="/offers", tags=["offers"])


def get_offer_service(db: Session = Depends(get_db)) -> OfferService:
    repository = OfferRepository(db)
    return OfferService(repository)


def get_candidate_service(db: Session = Depends(get_db)) -> CandidateService:
    repository = CandidateRepository(db)
    return CandidateService(repository)


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
def create_offer(
    payload: OfferCreate,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> Offer:
    candidate = candidate_service.get_by_id(str(payload.candidate_id))
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    offer = Offer(
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        offer_title=payload.offer_title,
        compensation_min=payload.compensation_min,
        compensation_max=payload.compensation_max,
        currency=payload.currency,
        expires_at=payload.expires_at,
        terms=payload.terms,
        created_by_id=current_user.id,
    )
    return service.create_offer(offer, author=current_user)


@router.get("/candidate/{candidate_id}", response_model=list[OfferResponse])
def list_candidate_offers(
    candidate_id: str,
    service: OfferService = Depends(get_offer_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> list[Offer]:
    candidate = candidate_service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return service.list_candidate_offers(candidate_id)


@router.get("/{offer_id}", response_model=OfferResponse)
def get_offer(
    offer_id: str,
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.patch("/{offer_id}", response_model=OfferResponse)
def update_offer(
    offer_id: str,
    payload: OfferUpdate,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    updates = payload.model_dump(exclude_unset=True)
    return service.update_offer(offer, updates)


@router.post("/{offer_id}/approve", response_model=OfferResponse)
def approve_offer(
    offer_id: str,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return service.approve_offer(offer, current_user)


@router.post("/{offer_id}/accept", response_model=OfferResponse)
def accept_offer(
    offer_id: str,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return service.accept_offer(offer, current_user)


@router.post("/{offer_id}/reject", response_model=OfferResponse)
def reject_offer(
    offer_id: str,
    reason: str | None = None,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return service.reject_offer(offer, current_user, reason=reason)


@router.post("/{offer_id}/withdraw", response_model=OfferResponse)
def withdraw_offer(
    offer_id: str,
    reason: str | None = None,
    current_user: User = Depends(get_current_user),
    service: OfferService = Depends(get_offer_service),
) -> Offer:
    offer = service.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return service.withdraw_offer(offer, current_user, reason=reason)
