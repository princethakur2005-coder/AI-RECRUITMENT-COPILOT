from __future__ import annotations

import asyncio
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def _app():
    return app


@pytest.fixture(scope="session")
def client(_app) -> Generator[TestClient, None, None]:
    with TestClient(_app) as c:
        yield c


@pytest.fixture
async def async_client(_app) -> AsyncClient:
    async with AsyncClient(app=_app, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Database test override placeholder. Tests that require DB should import get_db and use this fixture
@pytest.fixture
def db_session(monkeypatch):
    """Provide a lightweight transactional DB session using sqlite in-memory for tests.

    This is a placeholder: if the application uses SQLAlchemy, tests can override with a proper
    test engine and create tables as needed.
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.database import get_db
    except Exception:
        # If SQLAlchemy or app DB modules are not available, provide a no-op fixture
        yield None
        return

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(app, "dependency_overrides", getattr(app, "dependency_overrides", {}))
    app.dependency_overrides[get_db] = override_get_db

    yield SessionLocal


@pytest.fixture
def auth_headers():
    """Return a helper function to create Authorization headers for tests."""
    from app.core.jwt import create_access_token

    def _headers(subject: str | int = "test-user"):
        token = create_access_token(subject)
        return {"Authorization": f"Bearer {token}"}

    return _headers
