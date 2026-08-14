"""Shared fixtures/builders for Offer Management hardening tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application_status import ApplicationStatus
from app.core.security import hash_password
from app.db.base import Base

import app.models  # noqa: F401 — register all tables for metadata.create_all
from app.models.application import Application
from app.models.application_hiring_decision import ApplicationHiringDecision
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.job import Job
from app.models.offer import Offer
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.repositories.offer import OfferRepository
from app.repositories.notification import NotificationRepository
from app.schemas.offer import OfferCreate
from app.services.application import ApplicationService
from app.services.notification import NotificationService
from app.services.offer_service import OfferService


@pytest.fixture
def offer_db() -> Session:
    """Isolated in-memory SQLite session with FK enforcement for Offer tests."""
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
        session.close()
        engine.dispose()


class OfferWorld:
    """Tenant graph used by Offer lifecycle and API contract tests."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.company = self._create_company("Acme Hiring", "acme-hiring")
        self.other_company = self._create_company("Other Co", "other-co")

        self.recruiter = self._create_user("recruiter@acme.test", "Recruiter User")
        self.hiring_manager = self._create_user("hm@acme.test", "Hiring Manager")
        self.viewer = self._create_user("viewer@acme.test", "Viewer User")
        self.other_recruiter = self._create_user("recruiter@other.test", "Other Recruiter")
        # Legacy same-email User retained only to prove email matching is no longer authorization.
        self.candidate_user = self._create_user("candidate@example.com", "Candidate User")

        self.recruiter_member = self._create_member(self.company, self.recruiter, "recruiter")
        self.hm_member = self._create_member(self.company, self.hiring_manager, "hiring_manager")
        self.viewer_member = self._create_member(self.company, self.viewer, "interviewer")
        self.other_member = self._create_member(self.other_company, self.other_recruiter, "recruiter")

        self.job = self._create_job(self.company, self.recruiter_member, self.recruiter, "Backend Engineer")
        self.other_job = self._create_job(self.other_company, self.other_member, self.other_recruiter, "Other Role")

        self.candidate = self._create_candidate(
            "candidate@example.com",
            "Ada Lovelace",
            password="CandidatePass1!",
        )
        self.application = self._create_application(
            self.company,
            self.job,
            self.candidate,
            status=ApplicationStatus.INTERVIEW.value,
        )
        self.other_candidate = self._create_candidate(
            "other.cand@example.com",
            "Other Cand",
            password="OtherPass1!",
        )
        self.other_application = self._create_application(
            self.other_company,
            self.other_job,
            self.other_candidate,
            status=ApplicationStatus.INTERVIEW.value,
        )

        self.decision = self._create_hiring_decision(self.application, recommendation="Hire")
        self.other_decision = self._create_hiring_decision(self.other_application, recommendation="Hire")

        self.offer_service = self._build_offer_service()
        self.db.commit()

    def _build_offer_service(self) -> OfferService:
        application_repository = ApplicationRepository(self.db)
        member_repository = CompanyMemberRepository(self.db)
        notification_service = NotificationService(
            NotificationRepository(self.db),
            member_repository,
        )
        application_service = ApplicationService(
            application_repository,
            JobRepository(self.db),
            CandidateRepository(self.db),
            member_repository,
            notification_service=notification_service,
        )
        return OfferService(
            offer_repository=OfferRepository(self.db),
            application_repository=application_repository,
            member_repository=member_repository,
            hiring_decision_repository=ApplicationHiringDecisionRepository(self.db),
            application_service=application_service,
            notification_service=notification_service,
        )

    def _create_user(self, email: str, full_name: str) -> User:
        user = User(
            full_name=full_name,
            email=email,
            hashed_password="hashed",
            role="user",
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _create_company(self, name: str, slug: str) -> Company:
        owner = self._create_user(f"owner-{slug}@example.com", f"{name} Owner")
        company = Company(
            name=name,
            slug=slug,
            owner_id=owner.id,
            is_active=True,
        )
        self.db.add(company)
        self.db.flush()
        owner.company_id = company.id
        self.db.add(owner)
        self.db.flush()
        return company

    def _create_member(self, company: Company, user: User, role: str) -> CompanyMember:
        member = CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role=role,
            is_active=True,
        )
        self.db.add(member)
        self.db.flush()
        user.company_id = company.id
        self.db.add(user)
        self.db.flush()
        return member

    def _create_job(
        self,
        company: Company,
        member: CompanyMember,
        created_by: User,
        title: str,
    ) -> Job:
        job = Job(
            company_id=company.id,
            company_member_id=member.id,
            created_by_id=created_by.id,
            title=title,
            status="open",
            is_active=True,
            openings=1,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def _create_candidate(self, email: str, full_name: str, *, password: str | None = None) -> Candidate:
        parts = full_name.split(" ", 1)
        candidate = Candidate(
            first_name=parts[0],
            last_name=parts[1] if len(parts) > 1 else "Candidate",
            full_name=full_name,
            email=email,
            status="new",
            is_active=True,
            hashed_password=hash_password(password) if password else None,
        )
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def _create_application(
        self,
        company: Company,
        job: Job,
        candidate: Candidate,
        *,
        status: str,
    ) -> Application:
        application = Application(
            company_id=company.id,
            job_id=job.id,
            candidate_id=candidate.id,
            status=status,
            source="test",
        )
        self.db.add(application)
        self.db.flush()
        return application

    def _create_hiring_decision(
        self,
        application: Application,
        *,
        recommendation: str,
        override: dict | None = None,
    ) -> ApplicationHiringDecision:
        decision = ApplicationHiringDecision(
            application_id=application.id,
            recommendation=recommendation,
            overall_score=82,
            decision_confidence={
                "overall": 0.8,
                "ranking_confidence": 0.8,
                "semantic_confidence": 0.75,
                "evaluation_confidence": 0.7,
            },
            strengths=["Strong backend background"],
            weaknesses=[],
            missing_mandatory_qualifications=[],
            risk_factors=[],
            reasons={
                "ranking_contribution": 0.4,
                "evaluation_contribution": 0.35,
                "semantic_contribution": 0.15,
                "risk_penalty": 0.0,
                "final_score": 0.82,
            },
            recruiter_metadata={"summary": "Proceed", "next_step_hint": "Offer"},
            ai_hiring_summary=None,
            decision_detail={},
            recruiter_override=override,
            policy_version="1.0.0",
        )
        self.db.add(decision)
        self.db.flush()
        return decision

    def offer_payload(self, application_id=None) -> OfferCreate:
        return OfferCreate(
            application_id=application_id or self.application.id,
            offer_title="Backend Engineer Offer",
            compensation_min=100000,
            compensation_max=130000,
            currency="USD",
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            terms="Standard terms",
        )

    def refresh_application(self) -> Application:
        self.db.refresh(self.application)
        return self.application

    def count_active_offers(self, application_id=None) -> int:
        from sqlalchemy import func, select

        application_id = application_id or self.application.id
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Offer)
                .where(
                    Offer.application_id == application_id,
                    Offer.is_active.is_(True),
                )
            )
            or 0
        )


@pytest.fixture
def world(offer_db: Session) -> OfferWorld:
    return OfferWorld(offer_db)
