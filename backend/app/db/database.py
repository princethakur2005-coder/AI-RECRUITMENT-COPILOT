from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _should_use_sqlite_fallback(database_url: str) -> bool:
    if database_url.startswith("sqlite"):
        return False

    if not settings.DEBUG:
        return False

    try:
        parsed_url = make_url(database_url)
    except Exception:
        return False

    return parsed_url.host in {"localhost", "127.0.0.1", "::1", None}


def _create_database_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=False,
            pool_recycle=-1,
        )

    if settings.DEBUG and _should_use_sqlite_fallback(database_url):
        fallback_database_url = "sqlite:///./ai_recruitment_copilot_dev.db"
        return create_engine(
            fallback_database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=False,
            pool_recycle=-1,
        )

    if settings.DEBUG:
        try:
            engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=10,
                max_overflow=20,
            )
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return engine
        except OperationalError:
            fallback_database_url = "sqlite:///./ai_recruitment_copilot_dev.db"
            return create_engine(
                fallback_database_url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=False,
                pool_recycle=-1,
            )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )


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
    finally:
        db.close()
