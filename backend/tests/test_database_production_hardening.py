"""Database production hardening — migrations, constraints, sessions, and concurrency."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.database as database_module
import app.models  # noqa: F401
from app.core.notification import NotificationRecipientType
from app.db.base import Base
from app.db.database import get_db
from app.models.notification_preference import NotificationPreference
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.repositories.notification_preference import NotificationPreferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sqlite_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_alembic_has_single_head() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    heads = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1
    assert heads[0].startswith("m3n4o5p6q7r8")
    assert heads[0].endswith("(head)")


def test_candidate_notification_preferences_enforce_uniqueness(sqlite_db: Session) -> None:
    candidate_id = uuid4()
    first = NotificationPreference(
        recipient_type=NotificationRecipientType.CANDIDATE.value,
        recipient_id=candidate_id,
        company_id=None,
    )
    duplicate = NotificationPreference(
        recipient_type=NotificationRecipientType.CANDIDATE.value,
        recipient_id=candidate_id,
        company_id=None,
    )
    sqlite_db.add(first)
    sqlite_db.commit()
    sqlite_db.add(duplicate)
    with pytest.raises(IntegrityError):
        sqlite_db.commit()
    sqlite_db.rollback()


def test_notification_preference_get_or_create_is_idempotent(sqlite_db: Session) -> None:
    repo = NotificationPreferenceRepository(sqlite_db)
    candidate_id = uuid4()

    first = repo.get_or_create_for_candidate(candidate_id=candidate_id, commit=True)
    second = repo.get_or_create_for_candidate(candidate_id=candidate_id, commit=True)

    assert first.id == second.id
    rows = list(
        sqlite_db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.recipient_type == NotificationRecipientType.CANDIDATE.value,
                NotificationPreference.recipient_id == candidate_id,
            )
        ).all()
    )
    assert len(rows) == 1


def test_interview_calendar_sync_get_or_create_handles_race(sqlite_db: Session, monkeypatch) -> None:
    from app.models.interview_calendar_sync import InterviewCalendarSync
    from uuid import UUID

    interview_id = UUID("11111111-1111-4111-8111-111111111111")
    company_id = UUID("22222222-2222-4222-8222-222222222222")
    existing = InterviewCalendarSync(
        interview_id=interview_id,
        company_id=company_id,
        sync_status="pending",
    )
    repo = InterviewCalendarSyncRepository(sqlite_db)
    attempts = {"count": 0}

    def _create(_row, *, commit=True):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise IntegrityError("insert", {}, Exception("uq_interview_calendar_syncs_interview_id"))
        return existing

    monkeypatch.setattr(repo, "create", _create)
    monkeypatch.setattr(repo, "get_by_interview_id", lambda _interview_id: existing if attempts["count"] else None)

    first = repo.get_or_create_for_interview(
        interview_id=interview_id,
        company_id=company_id,
        calendar_integration_id=None,
        sync_status="pending",
        commit=True,
    )
    second = repo.get_or_create_for_interview(
        interview_id=interview_id,
        company_id=company_id,
        calendar_integration_id=None,
        sync_status="pending",
        commit=True,
    )
    assert first is existing
    assert second is existing


def test_get_db_rolls_back_on_exception(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(database_module, "SessionLocal", SessionLocal)

    generator = get_db()
    session = next(generator)
    session.add(
        NotificationPreference(
            recipient_type=NotificationRecipientType.CANDIDATE.value,
            recipient_id=uuid4(),
            company_id=None,
        )
    )
    session.flush()
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("request failed"))

    probe = SessionLocal()
    try:
        assert probe.scalar(select(func.count()).select_from(NotificationPreference)) == 0
    finally:
        probe.close()
