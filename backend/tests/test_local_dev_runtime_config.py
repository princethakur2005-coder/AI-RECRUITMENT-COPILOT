import importlib


def test_backend_host_is_allowed_from_json_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", '["localhost","127.0.0.1","testserver","backend"]')

    import app.core.config as config_module

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)

    assert config_module.settings.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "testserver", "backend"]


def test_debug_mode_falls_back_to_sqlite_when_postgres_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ai_user:ai_password@127.0.0.1:5432/ai_recruitment",
    )
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    import app.core.config as config_module
    import app.db.database as database_module
    from sqlalchemy.exc import OperationalError

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)
    importlib.reload(database_module)

    real_create_engine = database_module.create_engine

    def _failing_postgres_engine(url, *args, **kwargs):  # noqa: ANN001
        url_text = str(url)
        if url_text.startswith("postgresql"):
            engine = real_create_engine("sqlite://", connect_args={"check_same_thread": False})

            class _FailingConnection:
                def __enter__(self):
                    raise OperationalError("SELECT 1", {}, Exception("postgres unavailable"))

                def __exit__(self, *exc):  # noqa: ANN001
                    return False

            engine.connect = lambda: _FailingConnection()  # type: ignore[method-assign]
            return engine
        return real_create_engine(url, *args, **kwargs)

    monkeypatch.setattr(database_module, "create_engine", _failing_postgres_engine)

    assert config_module.settings.is_debug is True
    engine = database_module._create_database_engine(config_module.settings.DATABASE_URL)
    assert engine.url.drivername == "sqlite"


def test_debug_mode_uses_postgres_when_available(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ai_user:ai_password@localhost:5432/ai_recruitment",
    )
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    import app.core.config as config_module
    import app.db.database as database_module
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    try:
        probe = create_engine(
            "postgresql+psycopg2://ai_user:ai_password@localhost:5432/ai_recruitment",
            pool_pre_ping=True,
        )
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
        probe.dispose()
    except OperationalError:
        import pytest

        pytest.skip("Local PostgreSQL is not available")

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)
    importlib.reload(database_module)

    assert config_module.settings.is_debug is True
    # Prefer live Postgres when the local Docker DB is reachable.
    assert database_module.engine.url.drivername.startswith("postgresql")
