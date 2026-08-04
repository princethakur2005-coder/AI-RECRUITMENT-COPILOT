from __future__ import annotations

import re
from uuid import UUID

from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.user import User
from app.repositories.company import CompanyRepository
from app.repositories.user import UserRepository
from app.schemas.company import CompanyCreate

COMPANY_ADMIN_ROLE = "company_admin"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "company"


class CompanyService:
    """Service for company onboarding and tenant management."""

    def __init__(self, company_repository: CompanyRepository, user_repository: UserRepository) -> None:
        self.company_repository = company_repository
        self.user_repository = user_repository

    def user_has_company(self, user: User) -> bool:
        return user.company_id is not None

    def _build_unique_slug(self, name: str) -> str:
        base_slug = _slugify(name)
        slug = base_slug
        suffix = 1
        while self.company_repository.slug_exists(slug):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        return slug

    def create_company(self, owner: User, payload: CompanyCreate) -> Company:
        if self.user_has_company(owner):
            raise ValueError("User already belongs to a company")

        if self.company_repository.get_by_owner_id(owner.id):
            raise ValueError("User already owns a company")

        company = Company(
            name=payload.name.strip(),
            slug=self._build_unique_slug(payload.name),
            legal_name=payload.legal_name.strip() if payload.legal_name else None,
            website=str(payload.website) if payload.website else None,
            industry=payload.industry,
            company_size=payload.company_size,
            country=payload.country,
            timezone=payload.timezone,
            owner_id=owner.id,
            is_active=True,
        )

        db = self.company_repository.db
        try:
            db.add(company)
            db.flush()
            owner.company_id = company.id
            owner.role = COMPANY_ADMIN_ROLE
            db.add(owner)
            db.add(
                CompanyMember(
                    company_id=company.id,
                    user_id=owner.id,
                    role=COMPANY_ADMIN_ROLE,
                    is_active=True,
                )
            )
            db.commit()
            db.refresh(company)
            return company
        except Exception:
            db.rollback()
            raise

    def get_by_id(self, company_id: UUID) -> Company | None:
        return self.company_repository.get_by_id(company_id)
