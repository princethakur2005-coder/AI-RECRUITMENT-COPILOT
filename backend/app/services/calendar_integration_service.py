"""Tenant-scoped calendar integration management (no OAuth UI)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from app.core.audit import AUDIT_ACTOR_USER, AuditAction, AuditResourceType
from app.core.calendar import CalendarIntegrationStatus, CalendarProviderType
from app.core.config import Settings, get_settings
from app.core.secret_box import seal_secret
from app.models.calendar_integration import CalendarIntegration
from app.models.user import User
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.schemas.calendar import CalendarIntegrationCreate, CalendarIntegrationResponse
from app.services.audit_service import emit_audit

COMPANY_ADMIN_ROLE = "company_admin"


class CalendarIntegrationService:
    """CRUD for Company → CalendarIntegration. Secrets sealed; never returned."""

    def __init__(
        self,
        integration_repository: CalendarIntegrationRepository,
        company_repository: CompanyRepository,
        member_repository: CompanyMemberRepository,
        settings: Settings | None = None,
    ) -> None:
        self.integration_repository = integration_repository
        self.company_repository = company_repository
        self.member_repository = member_repository
        self.settings = settings or get_settings()

    def create(
        self,
        actor: User,
        company_id: UUID,
        payload: CalendarIntegrationCreate,
    ) -> CalendarIntegrationResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)

        existing = self.integration_repository.get_by_company_and_provider(
            company_id,
            payload.provider_type.value,
        )
        if existing is not None:
            raise ValueError(
                f"Calendar integration for provider '{payload.provider_type.value}' already exists"
            )

        sealed = None
        if payload.credentials:
            sealed = seal_secret(
                json.dumps(payload.credentials, separators=(",", ":"), sort_keys=True),
                self.settings.SECRET_KEY,
            )

        row = CalendarIntegration(
            company_id=company_id,
            provider_type=payload.provider_type.value,
            status=CalendarIntegrationStatus.ACTIVE.value,
            display_name=payload.display_name,
            external_calendar_id=payload.external_calendar_id,
            credentials_sealed=sealed,
            metadata_json=dict(payload.metadata or {}),
        )
        created = self.integration_repository.create(row)
        emit_audit(
            self.integration_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.CALENDAR_INTEGRATION_CREATED.value,
            resource_type=AuditResourceType.CALENDAR_INTEGRATION.value,
            resource_id=created.id,
            metadata={
                "provider_type": created.provider_type,
                "status": created.status,
                "display_name": created.display_name,
                "credentials_configured": sealed is not None,
            },
        )
        return CalendarIntegrationResponse.from_orm_row(created)

    def list(self, actor: User, company_id: UUID) -> list[CalendarIntegrationResponse]:
        self._get_company_or_raise(company_id)
        self._assert_company_access(actor, company_id)
        return [
            CalendarIntegrationResponse.from_orm_row(row)
            for row in self.integration_repository.list_by_company(company_id)
        ]

    def get(
        self,
        actor: User,
        company_id: UUID,
        integration_id: UUID,
    ) -> CalendarIntegrationResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_access(actor, company_id)
        row = self._get_owned_or_raise(integration_id, company_id)
        return CalendarIntegrationResponse.from_orm_row(row)

    def disable(self, actor: User, company_id: UUID, integration_id: UUID) -> CalendarIntegrationResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        row = self._get_owned_or_raise(integration_id, company_id)
        updated = self.integration_repository.update(
            row,
            {
                "status": CalendarIntegrationStatus.DISABLED.value,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        emit_audit(
            self.integration_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.CALENDAR_INTEGRATION_DISABLED.value,
            resource_type=AuditResourceType.CALENDAR_INTEGRATION.value,
            resource_id=updated.id,
            metadata={
                "provider_type": updated.provider_type,
                "status": updated.status,
            },
        )
        return CalendarIntegrationResponse.from_orm_row(updated)

    def delete(self, actor: User, company_id: UUID, integration_id: UUID) -> None:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        row = self._get_owned_or_raise(integration_id, company_id)
        provider_type = row.provider_type
        self.integration_repository.delete(row)
        emit_audit(
            self.integration_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.CALENDAR_INTEGRATION_DELETED.value,
            resource_type=AuditResourceType.CALENDAR_INTEGRATION.value,
            resource_id=integration_id,
            metadata={"provider_type": provider_type},
        )

    def _get_company_or_raise(self, company_id: UUID):
        company = self.company_repository.get_by_id(company_id)
        if not company:
            raise LookupError("Company not found")
        return company

    def _get_owned_or_raise(self, integration_id: UUID, company_id: UUID) -> CalendarIntegration:
        row = self.integration_repository.get_for_company(integration_id, company_id)
        if row is None:
            raise LookupError("Calendar integration not found")
        return row

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
            raise PermissionError("Only company admins can manage calendar integrations")

    def _assert_company_access(self, user: User, company_id: UUID) -> None:
        if not self._user_has_company_access(user, company_id):
            raise PermissionError("User does not belong to this company")
