from __future__ import annotations

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "gw0")


@pytest.fixture(scope="session")
def integration_db_engine(worker_id: str):
    """Create a per-worker sqlite database file and configure app DB engine to use it.

    This fixture sets `app.db.database.engine` and `SessionLocal` to use the test engine.
    Tables are created from the ORM `Base` metadata. Clean-up removes the file when done.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Create a worker-specific temp file for sqlite to support parallel runs
    tmpdir = tempfile.gettempdir()
    db_path = os.path.join(tmpdir, f"test_db_{worker_id}.db")
    db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Bind metadata
    try:
        from app.db.base import Base

        Base.metadata.create_all(bind=engine)
    except Exception:
        # If models or Base are unavailable, proceed silently
        pass

    # Patch application DB engine and SessionLocal
    try:
        import app.db.database as database_mod

        database_mod.engine = engine
        database_mod.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    except Exception:
        pass

    yield engine

    try:
        # dispose engine and remove file
        engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def db_session(integration_db_engine) -> Generator:
    """Yield a SQLAlchemy session wrapped in a rollback transaction per test for isolation."""
    from sqlalchemy.orm import Session
    from sqlalchemy import text
    import app.db.database as database_mod

    engine = integration_db_engine
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = database_mod.SessionLocal
    session: Session = SessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session) -> Generator[TestClient, None, None]:
    """Provide a TestClient instance with the DB dependency overridden to use the test session."""
    try:
        from app.db.database import get_db
    except Exception:
        get_db = None

    # Override get_db to yield the session from our fixture
    if get_db is not None:
        def _override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def auth_headers():
    from app.core.jwt import create_access_token

    def _make(sub: str | int = "test-user"):
        token = create_access_token(sub)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def override_dependency():
    """Helper to override FastAPI dependencies during tests.

    Usage:
        override_dependency(dependency, replacement_callable)
    """
    overrides = {}

    def _override(dep, replacement):
        app.dependency_overrides[dep] = replacement
        overrides[dep] = replacement

    yield _override

    # teardown
    for dep in list(overrides):
        app.dependency_overrides.pop(dep, None)
