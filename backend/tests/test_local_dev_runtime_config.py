import importlib
import os


def test_backend_host_is_allowed_from_json_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", '["localhost","127.0.0.1","testserver","backend"]')

    import app.core.config as config_module

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)

    assert config_module.settings.ALLOWED_HOSTS == ["localhost", "127.0.0.1", "testserver", "backend"]


def test_debug_mode_falls_back_to_sqlite_when_postgres_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://ai_user:ai_password@localhost:5432/ai_recruitment")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    import app.core.config as config_module
    import app.db.database as database_module

    config_module.get_settings.cache_clear()
    importlib.reload(config_module)
    importlib.reload(database_module)

    assert config_module.settings.is_debug is True
    assert database_module.engine.url.drivername == "sqlite"
