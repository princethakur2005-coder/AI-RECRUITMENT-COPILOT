from __future__ import annotations

from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.jwt import create_access_token
from app.core.security import hash_password, verify_password
from app.models.candidate import Candidate
from app.repositories.candidate import CandidateRepository
from app.services.audit_service import audit_service


class CandidateAuthenticationService:
    """Candidate identity authentication and account activation.

    Candidates are global contact identities (email-unique). Authorization for
    applications/offers remains scoped through Application ownership — never via
    a client-supplied company_id.
    """

    def __init__(self, candidate_repository: CandidateRepository) -> None:
        self.candidate_repository = candidate_repository

    def authenticate(self, email: str, password: str) -> str | None:
        candidate = self.candidate_repository.get_by_email(email)
        if candidate is None or not candidate.is_active:
            return None
        if not candidate.hashed_password:
            return None
        if not verify_password(password, candidate.hashed_password):
            return None

        token = create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)
        audit_service.log(
            actor_id=str(candidate.id),
            actor_type="candidate",
            action="candidate_login",
            resource_type="candidate",
            resource_id=str(candidate.id),
            metadata={"email": candidate.email},
        )
        return token

    def register_or_activate(
        self,
        *,
        full_name: str,
        email: str,
        password: str,
    ) -> tuple[Candidate, str] | None:
        """Create a candidate account or activate credentials on an existing profile.

        Returns None when an activated account already exists for the email.
        """
        normalized_email = email.strip().lower()
        full_name_clean = " ".join(full_name.split()).strip()
        first_name, last_name = self._split_name(full_name_clean)

        existing = self.candidate_repository.get_by_email(normalized_email)
        if existing is not None and existing.hashed_password:
            return None

        hashed = hash_password(password)
        if existing is None:
            candidate = Candidate(
                first_name=first_name or "Candidate",
                last_name=last_name or "",
                full_name=full_name_clean or normalized_email,
                email=normalized_email,
                status="new",
                is_active=True,
                hashed_password=hashed,
            )
            candidate = self.candidate_repository.create(candidate)
            action = "candidate_account_created"
        else:
            updates: dict[str, object] = {"hashed_password": hashed}
            if full_name_clean:
                updates["full_name"] = full_name_clean
                updates["first_name"] = first_name or existing.first_name
                updates["last_name"] = last_name or existing.last_name
            if not existing.is_active:
                # Explicitly refuse activation of deactivated identities.
                return None
            candidate = self.candidate_repository.update(existing, updates)
            action = "candidate_account_activated"

        token = create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)
        audit_service.log(
            actor_id=str(candidate.id),
            actor_type="candidate",
            action=action,
            resource_type="candidate",
            resource_id=str(candidate.id),
            metadata={"email": candidate.email},
        )
        return candidate, token

    def issue_token(self, candidate: Candidate) -> str:
        return create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        parts = full_name.split()
        if not parts:
            return "Candidate", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])
