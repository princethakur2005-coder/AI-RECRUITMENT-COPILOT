import logging
import os
from contextvars import ContextVar
from logging.config import dictConfig
from datetime import datetime, timezone
import json

from app.core.config import settings


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key in ("event", "method", "path", "status_code", "duration_ms", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _build_logging_config() -> dict:
    formatters = {
        "json": {
            "()": "app.core.logging.JsonFormatter",
        },
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if settings.LOG_JSON else "default",
            "stream": "ext://sys.stdout",
        }
    }

    configured_handlers = ["console"]

    if settings.LOG_ROTATION_ENABLED:
        file_dir = os.path.dirname(settings.LOG_FILE_PATH)
        if file_dir:
            os.makedirs(file_dir, exist_ok=True)
        handlers["rotating_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json" if settings.LOG_JSON else "default",
            "filename": settings.LOG_FILE_PATH,
            "maxBytes": settings.LOG_ROTATION_MAX_BYTES,
            "backupCount": settings.LOG_ROTATION_BACKUP_COUNT,
            "encoding": "utf-8",
        }
        configured_handlers.append("rotating_file")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "loggers": {
            "app": {
                "handlers": configured_handlers,
                "level": settings.LOG_LEVEL,
                "propagate": False,
            }
        },
        "root": {
            "handlers": configured_handlers,
            "level": settings.LOG_LEVEL,
        },
    }


LOGGING_CONFIG = _build_logging_config()


def configure_logging() -> None:
    dictConfig(LOGGING_CONFIG)


def set_request_id(request_id: str) -> None:
    request_id_context.set(request_id)


def get_request_id() -> str:
    return request_id_context.get()


logger = logging.getLogger("app")
