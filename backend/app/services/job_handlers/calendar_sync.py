"""Execute calendar.sync durable jobs via CalendarProvider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.calendar import CalendarSyncOperation, CalendarSyncStatus
from app.core.config import get_settings
from app.core.durable_job import JobExecutionError
from app.core.secret_box import unseal_secret
from app.models.durable_job import DurableJob
from app.models.interview_calendar_sync import InterviewCalendarSync
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.schemas.calendar import CalendarEventRequest, CalendarProviderError
from app.services.calendar_provider import (
    FakeCalendarProvider,
    build_calendar_provider,
)
from app.services.calendar_sync import CalendarSyncService

logger = logging.getLogger("app.calendar_sync_handler")


class CalendarSyncJobHandler:
    """Loads integration + interview server-side; never trusts payload credentials."""

    def __init__(
        self,
        db: Session,
        *,
        fake_provider: FakeCalendarProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.sync_repository = InterviewCalendarSyncRepository(db)
        self.integration_repository = CalendarIntegrationRepository(db)
        self.interview_repository = InterviewRepository(db)
        self.calendar_sync = CalendarSyncService(
            self.sync_repository,
            self.integration_repository,
            self.interview_repository,
        )
        self.fake_provider = fake_provider

    def execute(self, job: DurableJob) -> None:
        payload = job.payload or {}
        operation_raw = payload.get("operation")
        interview_id_raw = payload.get("interview_id")
        company_id_raw = payload.get("company_id")
        sync_id_raw = payload.get("sync_id")
        integration_id_raw = payload.get("integration_id")
        allow_missing = bool(payload.get("allow_missing_interview"))

        if not operation_raw or not interview_id_raw or not company_id_raw:
            raise JobExecutionError(
                "Calendar sync job missing required fields",
                retryable=False,
                error_code="invalid_payload",
            )

        try:
            operation = CalendarSyncOperation(str(operation_raw))
            interview_id = UUID(str(interview_id_raw))
            company_id = UUID(str(company_id_raw))
            sync_id = UUID(str(sync_id_raw)) if sync_id_raw else None
            integration_id = UUID(str(integration_id_raw)) if integration_id_raw else None
        except ValueError as exc:
            raise JobExecutionError(
                "Invalid calendar sync job identifiers",
                retryable=False,
                error_code="invalid_payload",
            ) from exc

        if job.company_id is not None and job.company_id != company_id:
            raise JobExecutionError(
                "Calendar sync company mismatch",
                retryable=False,
                error_code="tenant_mismatch",
            )

        integration = None
        if integration_id is not None:
            integration = self.integration_repository.get_for_company(integration_id, company_id)
        if integration is None:
            integration = self.integration_repository.get_active_for_company(company_id)
        if integration is None:
            self._mark_sync(
                sync_id,
                interview_id,
                status=CalendarSyncStatus.NOT_CONNECTED,
                operation=operation,
            )
            return

        # Resolve credentials server-side only (never logged).
        if integration.credentials_sealed:
            try:
                unseal_secret(integration.credentials_sealed, self.settings.SECRET_KEY)
            except ValueError as exc:
                raise JobExecutionError(
                    "Calendar credentials unavailable",
                    retryable=False,
                    error_code="credentials_unseal_failed",
                ) from exc

        provider = build_calendar_provider(
            integration.provider_type,
            fake_provider=self.fake_provider,
        )

        interview = self.interview_repository.get_by_id_for_company(interview_id, company_id)
        sync = None
        if sync_id is not None:
            sync = self.sync_repository.get_for_company(sync_id, company_id)
        if sync is None:
            sync = self.sync_repository.get_by_interview_id(interview_id)

        external_event_id = None
        if sync is not None and sync.external_event_id:
            external_event_id = sync.external_event_id
        elif payload.get("external_event_id"):
            external_event_id = str(payload["external_event_id"])

        if interview is None:
            if operation == CalendarSyncOperation.CANCEL and (
                allow_missing or external_event_id
            ):
                request = CalendarEventRequest(
                    interview_id=interview_id,
                    company_id=company_id,
                    title="Interview",
                    start_at=datetime.now(timezone.utc),
                    end_at=datetime.now(timezone.utc),
                    timezone="UTC",
                    external_event_id=external_event_id,
                    external_calendar_id=integration.external_calendar_id,
                )
                try:
                    provider.cancel_event(request)
                except CalendarProviderError as exc:
                    raise JobExecutionError(
                        str(exc),
                        retryable=exc.retryable,
                        error_code=exc.error_code or "calendar_provider_error",
                    ) from exc
                if sync is not None:
                    self._mark_sync(
                        sync.id,
                        interview_id,
                        status=CalendarSyncStatus.CANCELLED,
                        operation=operation,
                        external_event_id=external_event_id,
                    )
                return
            raise JobExecutionError(
                "Interview not found for calendar sync",
                retryable=False,
                error_code="interview_not_found",
            )

        request = self.calendar_sync.build_event_request(
            interview,
            external_event_id=external_event_id,
            external_calendar_id=integration.external_calendar_id,
        )

        try:
            if operation == CalendarSyncOperation.CREATE:
                # Idempotent: if already synced with external id, treat create as success.
                if sync is not None and sync.external_event_id and sync.sync_status == CalendarSyncStatus.SYNCED.value:
                    return
                result = provider.create_event(request)
                self._persist_success(
                    sync_id=sync.id if sync else None,
                    interview_id=interview_id,
                    company_id=company_id,
                    integration_id=integration.id,
                    operation=operation,
                    external_event_id=result.external_event_id,
                    existing_external_event_id=sync.external_event_id if sync else None,
                )
            elif operation == CalendarSyncOperation.UPDATE:
                if not request.external_event_id:
                    result = provider.create_event(request)
                else:
                    result = provider.update_event(request)
                self._persist_success(
                    sync_id=sync.id if sync else None,
                    interview_id=interview_id,
                    company_id=company_id,
                    integration_id=integration.id,
                    operation=operation,
                    external_event_id=result.external_event_id,
                    existing_external_event_id=sync.external_event_id if sync else None,
                )
            elif operation == CalendarSyncOperation.CANCEL:
                result = provider.cancel_event(request)
                self._persist_success(
                    sync_id=sync.id if sync else None,
                    interview_id=interview_id,
                    company_id=company_id,
                    integration_id=integration.id,
                    operation=operation,
                    external_event_id=result.external_event_id,
                    existing_external_event_id=sync.external_event_id if sync else None,
                    final_status=CalendarSyncStatus.CANCELLED,
                )
            else:
                raise JobExecutionError(
                    f"Unsupported calendar sync operation: {operation}",
                    retryable=False,
                    error_code="invalid_operation",
                )
        except CalendarProviderError as exc:
            self._mark_sync(
                sync.id if sync else None,
                interview_id,
                status=CalendarSyncStatus.FAILED,
                operation=operation,
                error_code=exc.error_code,
                error_message=str(exc),
            )
            raise JobExecutionError(
                str(exc),
                retryable=exc.retryable,
                error_code=exc.error_code or "calendar_provider_error",
            ) from exc

    def _persist_success(
        self,
        *,
        sync_id: UUID | None,
        interview_id: UUID,
        company_id: UUID,
        integration_id: UUID,
        operation: CalendarSyncOperation,
        external_event_id: str,
        existing_external_event_id: str | None,
        final_status: CalendarSyncStatus = CalendarSyncStatus.SYNCED,
    ) -> None:
        now = datetime.now(timezone.utc)
        # Never silently overwrite a different external event id.
        if existing_external_event_id and existing_external_event_id != external_event_id:
            if operation == CalendarSyncOperation.CREATE:
                resolved_external_id = existing_external_event_id
            else:
                resolved_external_id = existing_external_event_id
        else:
            resolved_external_id = existing_external_event_id or external_event_id

        if sync_id is not None:
            sync = self.sync_repository.get_by_id(sync_id)
        else:
            sync = self.sync_repository.get_by_interview_id(interview_id)

        if sync is None:
            sync = self.sync_repository.create(
                InterviewCalendarSync(
                    interview_id=interview_id,
                    company_id=company_id,
                    calendar_integration_id=integration_id,
                    sync_status=final_status.value,
                    external_event_id=resolved_external_id,
                    last_operation=operation.value,
                    last_synced_at=now,
                ),
                commit=False,
            )
            return

        self.sync_repository.update(
            sync,
            {
                "calendar_integration_id": integration_id,
                "sync_status": final_status.value,
                "external_event_id": resolved_external_id,
                "last_operation": operation.value,
                "last_error_code": None,
                "last_error_message": None,
                "last_synced_at": now,
                "updated_at": now,
            },
            commit=False,
        )

    def _mark_sync(
        self,
        sync_id: UUID | None,
        interview_id: UUID,
        *,
        status: CalendarSyncStatus,
        operation: CalendarSyncOperation,
        external_event_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        sync = None
        if sync_id is not None:
            sync = self.sync_repository.get_by_id(sync_id)
        if sync is None:
            sync = self.sync_repository.get_by_interview_id(interview_id)
        if sync is None:
            return
        updates: dict = {
            "sync_status": status.value,
            "last_operation": operation.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if external_event_id is not None and not sync.external_event_id:
            updates["external_event_id"] = external_event_id
        if error_code is not None:
            updates["last_error_code"] = error_code
        if error_message is not None:
            updates["last_error_message"] = error_message[:2000]
        if status in {CalendarSyncStatus.SYNCED, CalendarSyncStatus.CANCELLED}:
            updates["last_synced_at"] = datetime.now(timezone.utc)
            updates["last_error_code"] = None
            updates["last_error_message"] = None
        self.sync_repository.update(sync, updates, commit=False)
