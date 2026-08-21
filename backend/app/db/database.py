from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _should_allow_sqlite_fallback(database_url: str) -> bool:
    """Allow SQLite fallback only for local DEBUG Postgres URLs."""
    if database_url.startswith("sqlite"):
        return False

    if not settings.DEBUG:
        return False

    try:
        parsed_url = make_url(database_url)
    except Exception:
        return False

    return parsed_url.host in {"localhost", "127.0.0.1", "::1", None}


def _create_sqlite_fallback_engine() -> Engine:
    return create_engine(
        "sqlite:///./ai_recruitment_copilot_dev.db",
        connect_args={"check_same_thread": False},
        pool_pre_ping=False,
        pool_recycle=-1,
    )


def _create_database_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=False,
            pool_recycle=-1,
        )

    # Prefer the configured database (PostgreSQL). Fall back to local SQLite only
    # when DEBUG local Postgres is unreachable — never skip a healthy Postgres.
    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=settings.DB_POOL_SIZE if not settings.DEBUG else 10,
            max_overflow=settings.DB_MAX_OVERFLOW if not settings.DEBUG else 20,
            pool_timeout=settings.DB_POOL_TIMEOUT,
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine
    except OperationalError:
        if _should_allow_sqlite_fallback(database_url):
            return _create_sqlite_fallback_engine()
        raise


engine: Engine = _create_database_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for dependency injection."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
