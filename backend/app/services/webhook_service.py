"""Tenant-scoped webhook configuration management."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from app.core.audit import AUDIT_ACTOR_USER, AuditAction, AuditResourceType
from app.core.config import Settings, get_settings
from app.core.secret_box import seal_secret
from app.core.webhook import validate_webhook_endpoint_url
from app.models.user import User
from app.models.webhook import Webhook
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.webhook import WebhookRepository
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookResponse,
    WebhookUpdate,
)
from app.services.audit_service import emit_audit

COMPANY_ADMIN_ROLE = "company_admin"


class WebhookService:
    """CRUD + enable/disable for Company → Webhook ownership boundary."""

    def __init__(
        self,
        webhook_repository: WebhookRepository,
        company_repository: CompanyRepository,
        member_repository: CompanyMemberRepository,
        settings: Settings | None = None,
    ) -> None:
        self.webhook_repository = webhook_repository
        self.company_repository = company_repository
        self.member_repository = member_repository
        self.settings = settings or get_settings()

    def create(self, actor: User, company_id: UUID, payload: WebhookCreate) -> WebhookCreatedResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        url = self._validate_url(payload.url)

        signing_secret = secrets.token_urlsafe(32)
        sealed = seal_secret(signing_secret, self.settings.SECRET_KEY)
        hint = signing_secret[-4:]

        row = Webhook(
            company_id=company_id,
            url=url,
            description=payload.description.strip() if payload.description else None,
            is_active=payload.is_active,
            event_types_json=list(payload.event_types),
            signing_secret_sealed=sealed,
            secret_hint=hint,
            metadata_json=dict(payload.metadata or {}),
        )
        created = self.webhook_repository.create(row)
        emit_audit(
            self.webhook_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.WEBHOOK_CREATED.value,
            resource_type=AuditResourceType.WEBHOOK.value,
            resource_id=created.id,
            metadata={
                "url": created.url,
                "is_active": created.is_active,
                "event_types": list(created.event_types_json or []),
                "secret_hint": created.secret_hint,
            },
        )
        response = WebhookCreatedResponse(
            **WebhookResponse.from_orm_webhook(created).model_dump(),
            signing_secret=signing_secret,
        )
        return response

    def list(self, actor: User, company_id: UUID) -> list[WebhookResponse]:
        self._get_company_or_raise(company_id)
        self._assert_company_access(actor, company_id)
        return [
            WebhookResponse.from_orm_webhook(row)
            for row in self.webhook_repository.list_by_company(company_id)
        ]

    def get(self, actor: User, company_id: UUID, webhook_id: UUID) -> WebhookResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_access(actor, company_id)
        row = self._get_owned_or_raise(webhook_id, company_id)
        return WebhookResponse.from_orm_webhook(row)

    def update(
        self,
        actor: User,
        company_id: UUID,
        webhook_id: UUID,
        payload: WebhookUpdate,
    ) -> WebhookResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        row = self._get_owned_or_raise(webhook_id, company_id)

        updates: dict = {"updated_at": datetime.now(timezone.utc)}
        if payload.url is not None:
            updates["url"] = self._validate_url(payload.url)
        if payload.description is not None:
            updates["description"] = payload.description.strip() or None
        if payload.event_types is not None:
            updates["event_types_json"] = list(payload.event_types)
        if payload.metadata is not None:
            updates["metadata_json"] = dict(payload.metadata)

        updated = self.webhook_repository.update(row, updates)
        emit_audit(
            self.webhook_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.WEBHOOK_UPDATED.value,
            resource_type=AuditResourceType.WEBHOOK.value,
            resource_id=updated.id,
            metadata={
                "updated_fields": sorted(k for k in updates if k != "updated_at"),
                "url": updated.url,
                "event_types": list(updated.event_types_json or []),
            },
        )
        return WebhookResponse.from_orm_webhook(updated)

    def set_active(
        self,
        actor: User,
        company_id: UUID,
        webhook_id: UUID,
        *,
        is_active: bool,
    ) -> WebhookResponse:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        row = self._get_owned_or_raise(webhook_id, company_id)
        updated = self.webhook_repository.update(
            row,
            {
                "is_active": is_active,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        emit_audit(
            self.webhook_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=(
                AuditAction.WEBHOOK_ACTIVATED.value
                if is_active
                else AuditAction.WEBHOOK_DEACTIVATED.value
            ),
            resource_type=AuditResourceType.WEBHOOK.value,
            resource_id=updated.id,
            metadata={"is_active": updated.is_active},
        )
        return WebhookResponse.from_orm_webhook(updated)

    def delete(self, actor: User, company_id: UUID, webhook_id: UUID) -> None:
        self._get_company_or_raise(company_id)
        self._assert_company_admin(actor, company_id)
        row = self._get_owned_or_raise(webhook_id, company_id)
        self.webhook_repository.delete(row)
        emit_audit(
            self.webhook_repository.db,
            company_id=company_id,
            actor_type=AUDIT_ACTOR_USER,
            actor_id=actor.id,
            action=AuditAction.WEBHOOK_DELETED.value,
            resource_type=AuditResourceType.WEBHOOK.value,
            resource_id=webhook_id,
            metadata={"url": row.url},
        )

    def _validate_url(self, url: str) -> str:
        allow_http = bool(self.settings.DEBUG) and bool(
            getattr(self.settings, "WEBHOOK_ALLOW_HTTP_LOCALHOST", True)
        )
        resolve_dns = bool(getattr(self.settings, "WEBHOOK_VALIDATE_DNS", True))
        # Tests / offline environments may disable DNS resolution.
        if bool(getattr(self.settings, "WEBHOOK_SKIP_DNS_VALIDATION", False)):
            resolve_dns = False
        return validate_webhook_endpoint_url(
            url,
            allow_http_localhost=allow_http,
            resolve_dns=resolve_dns,
        )

    def _get_company_or_raise(self, company_id: UUID):
        company = self.company_repository.get_by_id(company_id)
        if not company:
            raise LookupError("Company not found")
        return company

    def _get_owned_or_raise(self, webhook_id: UUID, company_id: UUID) -> Webhook:
        row = self.webhook_repository.get_for_company(webhook_id, company_id)
        if row is None:
            raise LookupError("Webhook not found")
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
            raise PermissionError("Only company admins can manage webhooks")

    def _assert_company_access(self, user: User, company_id: UUID) -> None:
        if not self._user_has_company_access(user, company_id):
            raise PermissionError("User does not belong to this company")
