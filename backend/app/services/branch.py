from __future__ import annotations

import re
from uuid import UUID

from app.models.branch import Branch
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company import CompanyRepository
from app.schemas.branch import BranchCreate

COMPANY_ADMIN_ROLE = "company_admin"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "branch"


class BranchService:
    """Service for company branch management."""

    def __init__(
        self,
        branch_repository: BranchRepository,
        company_repository: CompanyRepository,
    ) -> None:
        self.branch_repository = branch_repository
        self.company_repository = company_repository

    def _get_company_or_raise(self, company_id: UUID):
        company = self.company_repository.get_by_id(company_id)
        if not company:
            raise LookupError("Company not found")
        return company

    def _assert_company_member(self, user: User, company_id: UUID) -> None:
        if user.company_id != company_id:
            raise PermissionError("User does not belong to this company")

    def _assert_company_admin(self, user: User, company_id: UUID) -> None:
        self._assert_company_member(user, company_id)
        if user.role != COMPANY_ADMIN_ROLE:
            raise PermissionError("Only company admins can create branches")

    def _build_unique_slug(self, company_id: UUID, name: str) -> str:
        base_slug = _slugify(name)
        slug = base_slug
        suffix = 1
        while self.branch_repository.slug_exists_for_company(company_id, slug):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        return slug

    def create_branch(self, user: User, company_id: UUID, payload: BranchCreate) -> Branch:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(user, company_id)

        branch = Branch(
            company_id=company_id,
            name=payload.name.strip(),
            slug=self._build_unique_slug(company_id, payload.name),
            code=payload.code.strip() if payload.code else None,
            address_line1=payload.address_line1,
            address_line2=payload.address_line2,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            postal_code=payload.postal_code,
            timezone=payload.timezone,
            is_active=True,
        )
        return self.branch_repository.create(branch)

    def list_branches(self, user: User, company_id: UUID) -> list[Branch]:
        self._get_company_or_raise(company_id)
        self._assert_company_member(user, company_id)
        return self.branch_repository.list_by_company_id(company_id)
