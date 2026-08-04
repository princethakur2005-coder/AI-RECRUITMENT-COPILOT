from __future__ import annotations

from uuid import UUID

from app.models.company_member import CompanyMember
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.user import UserRepository
from app.schemas.company_member import CompanyMemberCreate

COMPANY_ADMIN_ROLE = "company_admin"
ALLOWED_MEMBER_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class CompanyMemberService:
    """Service for company membership and recruiter management."""

    def __init__(
        self,
        member_repository: CompanyMemberRepository,
        company_repository: CompanyRepository,
        user_repository: UserRepository,
        branch_repository: BranchRepository,
    ) -> None:
        self.member_repository = member_repository
        self.company_repository = company_repository
        self.user_repository = user_repository
        self.branch_repository = branch_repository

    def _get_company_or_raise(self, company_id: UUID):
        company = self.company_repository.get_by_id(company_id)
        if not company:
            raise LookupError("Company not found")
        return company

    def _user_is_company_admin(self, user: User, company_id: UUID) -> bool:
        membership = self.member_repository.get_by_company_and_user(company_id, user.id)
        if membership and membership.is_active and membership.role == COMPANY_ADMIN_ROLE:
            return True
        return user.company_id == company_id and user.role == COMPANY_ADMIN_ROLE

    def _user_has_company_access(self, user: User, company_id: UUID) -> bool:
        membership = self.member_repository.get_by_company_and_user(company_id, user.id)
        if membership and membership.is_active:
            return True
        return user.company_id == company_id

    def _assert_company_admin(self, user: User, company_id: UUID) -> None:
        if not self._user_is_company_admin(user, company_id):
            raise PermissionError("Only company admins can manage company members")

    def _assert_company_access(self, user: User, company_id: UUID) -> None:
        if not self._user_has_company_access(user, company_id):
            raise PermissionError("User does not belong to this company")

    def _validate_branch_for_company(self, company_id: UUID, branch_id: UUID) -> None:
        branch = self.branch_repository.get_by_id(branch_id)
        if not branch or branch.company_id != company_id:
            raise LookupError("Branch not found for this company")

    def add_member(self, actor: User, company_id: UUID, payload: CompanyMemberCreate) -> CompanyMember:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)

        role = payload.role.strip().lower()
        if role not in ALLOWED_MEMBER_ROLES:
            raise ValueError(f"Unsupported membership role: {payload.role}")

        target_user = self.user_repository.get_by_id(payload.user_id)
        if not target_user or not target_user.is_active:
            raise LookupError("User not found")

        if self.member_repository.get_by_company_and_user(company_id, payload.user_id):
            raise ValueError("User is already a member of this company")

        existing_membership = self.member_repository.get_by_user_id(payload.user_id)
        if existing_membership and existing_membership.company_id != company_id:
            raise ValueError("User already belongs to another company")

        if target_user.company_id and target_user.company_id != company_id:
            raise ValueError("User already belongs to another company")

        if payload.branch_id is not None:
            self._validate_branch_for_company(company_id, payload.branch_id)

        db = self.member_repository.db
        member = CompanyMember(
            company_id=company_id,
            user_id=payload.user_id,
            branch_id=payload.branch_id,
            role=role,
            is_active=True,
        )

        try:
            db.add(member)
            if target_user.company_id is None:
                target_user.company_id = company_id
                db.add(target_user)
            db.commit()
            db.refresh(member)
            member = self.member_repository.get_by_company_and_user(company_id, payload.user_id)
            if member is None:
                raise RuntimeError("Failed to load created company member")
            return member
        except Exception:
            db.rollback()
            raise

    def list_members(self, actor: User, company_id: UUID) -> list[CompanyMember]:
        self._get_company_or_raise(company_id)
        self._assert_company_access(actor, company_id)
        return self.member_repository.list_by_company_id(company_id)
