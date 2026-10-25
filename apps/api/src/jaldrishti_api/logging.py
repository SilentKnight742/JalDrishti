"""Small dependency-free JSON logging setup."""

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    _standard_fields = frozenset(logging.makeLogRecord({}).__dict__)

    def __init__(self, *, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self._service,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id is not None:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in self._standard_fields and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(*, level: str, service: str) -> None:
    """Configure application logging without mutating third-party records."""

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter(service=service))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_request_id(request_id: str) -> Token[str | None]:
    return request_id_context.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_context.reset(token)
