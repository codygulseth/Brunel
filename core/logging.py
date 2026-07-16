"""Central logging configuration with safe, structured context."""

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any
from config.settings import LoggingSettings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        standard_fields = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(settings: LoggingSettings) -> None:
    formatter = "json" if settings.json_output else "plain"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
                "json": {"()": JsonFormatter},
            },
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": formatter}},
            "root": {"handlers": ["console"], "level": settings.level},
        }
    )
