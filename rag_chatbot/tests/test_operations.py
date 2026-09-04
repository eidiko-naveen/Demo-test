from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.health import readiness, validate_startup


def test_startup_requires_qdrant_key_for_remote_store():
    settings = SimpleNamespace(
        qdrant_url="https://qdrant.example",
        qdrant_api_key=None,
        langfuse_enabled=False,
        langfuse_public_key=None,
        langfuse_secret_key=None,
        validate_runtime=lambda: None,
    )
    with patch("services.health.get_settings", return_value=settings), pytest.raises(ValueError, match="QDRANT_API_KEY"):
        validate_startup()


def test_startup_requires_langfuse_credentials_when_enabled():
    settings = SimpleNamespace(
        qdrant_url=None,
        qdrant_api_key=None,
        langfuse_enabled=True,
        langfuse_public_key=None,
        langfuse_secret_key=None,
        validate_runtime=lambda: None,
    )
    with patch("services.health.get_settings", return_value=settings), pytest.raises(ValueError, match="Langfuse"):
        validate_startup()


def test_readiness_reports_dependency_failure_without_secret_details():
    settings = SimpleNamespace(langfuse_enabled=False, langfuse_public_key=None, langfuse_secret_key=None)
    with patch("services.health.get_settings", return_value=settings), \
         patch("services.health.engine.connect", side_effect=RuntimeError("password=secret")), \
         patch("services.health.get_qdrant_client", side_effect=ConnectionError("token=secret")), \
         patch("services.health.get_search_provider", return_value=SimpleNamespace(enabled=False)), \
         patch("services.health.get_llm", side_effect=RuntimeError("token=secret")):
        result = readiness()
    assert result["database"] == "unavailable"
    assert result["qdrant"] == "unavailable"
    assert result["search_provider"] == "disabled"
    assert result["llm"] == "unavailable"
    assert result["langfuse"] == "disabled"
    assert result["ready"] == "degraded"
    assert "secret" not in str(result)
