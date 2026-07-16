from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.note import Note
from app.models.user import User
from app.repositories.note import NoteRepository
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate
from app.services.note_service import NoteService
from app.services.candidate import CandidateService
from app.repositories.candidate import CandidateRepository

router = APIRouter(prefix="/notes", tags=["notes"])


def get_note_service(db: Session = Depends(get_db)) -> NoteService:
    repository = NoteRepository(db)
    return NoteService(repository)


def get_candidate_service(db: Session = Depends(get_db)) -> CandidateService:
    repository = CandidateRepository(db)
    return CandidateService(repository)


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    current_user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> Note:
    candidate = candidate_service.get_by_id(str(payload.candidate_id))
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    note = Note(
        candidate_id=payload.candidate_id,
        author_id=current_user.id,
        content=payload.content,
        source=payload.source,
        pinned=payload.pinned,
        mentions=payload.mentions,
    )
    return service.create_note(note, author=current_user)


@router.get("/candidate/{candidate_id}", response_model=list[NoteResponse])
def list_candidate_notes(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> list[Note]:
    candidate = candidate_service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return service.list_candidate_notes(candidate_id)


@router.get("/candidate/{candidate_id}/pinned", response_model=list[NoteResponse])
def list_pinned_notes(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> list[Note]:
    candidate = candidate_service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return service.list_pinned_notes(candidate_id)


@router.patch("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: str,
    payload: NoteUpdate,
    current_user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
    db: Session = Depends(get_db),
) -> Note:
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    update_data = payload.model_dump(exclude_unset=True)
    return service.update_note(note, update_data)


@router.post("/suggest", response_model=dict)
def suggest_note(
    candidate_id: str,
    recruiter_context: str | None = None,
    mention_user_ids: list[str] | None = None,
    current_user: User = Depends(get_current_user),
    service: NoteService = Depends(get_note_service),
    candidate_service: CandidateService = Depends(get_candidate_service),
) -> dict:
    candidate = candidate_service.get_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return service.generate_suggested_note(
        candidate={
            "full_name": candidate.full_name,
            "summary": candidate.summary,
            "email": candidate.email,
        },
        recruiter_context=recruiter_context,
        mention_user_ids=mention_user_ids,
    )
