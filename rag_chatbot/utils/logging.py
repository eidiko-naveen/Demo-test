import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

_request_context: ContextVar[dict] = ContextVar("request_context", default={})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
            "tenant_id": getattr(record, "tenant_id", None),
            "session_id": getattr(record, "session_id", None),
        }
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=True)


@contextmanager
def request_context(**context):
    current = _request_context.get().copy()
    current.update({key: value for key, value in context.items() if value is not None})
    token = _request_context.set(current)
    try:
        yield current
    finally:
        _request_context.reset(token)


def get_request_context() -> dict:
    return _request_context.get().copy()


def bind_request_metadata(logger: logging.Logger, **context):
    metadata = get_request_context()
    metadata.update({key: value for key, value in context.items() if value is not None})
    return {"request_id": metadata.get("request_id") or str(uuid4()), "user_id": metadata.get("user_id"), "tenant_id": metadata.get("tenant_id"), "session_id": metadata.get("session_id")}


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def log(self, level: int, message: str, **context):
        metadata = bind_request_metadata(self.logger, **context)
        self.logger.log(level, message, extra={"request_id": metadata["request_id"], "user_id": metadata["user_id"], "tenant_id": metadata["tenant_id"], "session_id": metadata["session_id"], "extra": context})

    def info(self, message: str, **context):
        self.log(logging.INFO, message, **context)

    def warning(self, message: str, **context):
        self.log(logging.WARNING, message, **context)

    def error(self, message: str, **context):
        self.log(logging.ERROR, message, **context)

    def exception(self, message: str, **context):
        self.log(logging.ERROR, message, **context)
