from __future__ import annotations

import asyncio
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.middleware.security import reset_rate_limit_state


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


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
    """Provide a lightweight transactional DB session using sqlite in-memory for tests."""
    try:
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        import app.models  # noqa: F401
        from app.db.base import Base
        from app.db.database import get_db
    except Exception:
        yield None
        return

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
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.rollback()
            db.close()

    monkeypatch.setattr(app, "dependency_overrides", getattr(app, "dependency_overrides", {}))
    app.dependency_overrides[get_db] = override_get_db

    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.rollback()
        session.close()
        engine.dispose()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_headers():
    """Return a helper function to create Authorization headers for tests."""
    from app.core.jwt import create_access_token

    def _headers(subject: str | int = "test-user"):
        token = create_access_token(subject)
        return {"Authorization": f"Bearer {token}"}

    return _headers
