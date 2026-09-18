import logging
import time
from collections import defaultdict
from threading import Lock

from sqlalchemy import text

from config.settings import get_settings
from database.db import engine
from rag.engine import get_qdrant_client
from services.search import get_search_provider
from models.llm import get_llm

logger = logging.getLogger(__name__)

_METRICS = defaultdict(float)
_METRIC_LOCK = Lock()
_ALERTS: list[dict] = []


def record_metric(name: str, value: float = 1.0) -> None:
    with _METRIC_LOCK:
        _METRICS[name] += value


def record_latency(name: str, seconds: float) -> None:
    record_metric(f"latency_seconds.{name}", seconds)


def metrics_snapshot() -> dict[str, float]:
    with _METRIC_LOCK:
        return dict(_METRICS)


def emit_alert(name: str, message: str, **context) -> None:
    payload = {"alert": name, "message": message, **context}
    _ALERTS.append(payload)
    logger.error("alert %s: %s", name, message, extra={"extra": payload})


def get_alerts() -> list[dict]:
    return list(_ALERTS)


def validate_startup() -> None:
    settings = get_settings()
    settings.validate_runtime()
    if settings.qdrant_url and not settings.qdrant_api_key:
        raise ValueError("QDRANT_API_KEY is required when QDRANT_URL is configured")
    if settings.langfuse_enabled and not (settings.langfuse_public_key and settings.langfuse_secret_key):
        raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when Langfuse is enabled")


def health_check_db() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        logger.warning("database readiness check failed: %s", type(exc).__name__)
        return False, "unavailable"


def health_check_qdrant() -> tuple[bool, str]:
    try:
        client = get_qdrant_client()
        return client.get_collections() is not None, "ok" if client.get_collections() is not None else "unavailable"
    except Exception as exc:
        logger.warning("qdrant readiness check failed: %s", type(exc).__name__)
        return False, "unavailable"


def health_check_search() -> tuple[bool, str]:
    try:
        provider = get_search_provider()
        return getattr(provider, "enabled", False), "enabled" if getattr(provider, "enabled", False) else "disabled"
    except Exception as exc:
        logger.warning("search provider health check failed: %s", type(exc).__name__)
        return False, "unavailable"


def health_check_llm() -> tuple[bool, str]:
    try:
        llm = get_llm()
        return llm is not None, "ready" if llm is not None else "unavailable"
    except Exception as exc:
        logger.warning("llm health check failed: %s", type(exc).__name__)
        return False, "unavailable"


def readiness() -> dict[str, str]:
    status: dict[str, str] = {}
    db_ok, db_state = health_check_db()
    q_ok, q_state = health_check_qdrant()
    search_ok, search_state = health_check_search()
    llm_ok, llm_state = health_check_llm()
    status["database"] = db_state
    status["qdrant"] = q_state
    status["search_provider"] = search_state
    status["llm"] = llm_state
    settings = get_settings()
    status["langfuse"] = "configured" if settings.langfuse_enabled and settings.langfuse_public_key and settings.langfuse_secret_key else "disabled"
    status["ready"] = "ok" if db_ok and q_ok and llm_ok else "degraded"
    return status


def track_request(operation: str, user_id: str | None = None, tenant_id: str | None = None, session_id: str | None = None):
    start = time.perf_counter()

    def wrapper(func):
        def inner(*args, **kwargs):
            with __import__("contextlib").nullcontext():
                pass
            try:
                result = func(*args, **kwargs)
                record_metric(f"requests.{operation}", 1)
                record_latency(operation, time.perf_counter() - start)
                return result
            except Exception as exc:
                record_metric(f"failures.{operation}", 1)
                emit_alert(f"{operation}_failed", str(exc), user_id=user_id, tenant_id=tenant_id, session_id=session_id)
                raise
        return inner
    return wrapper
