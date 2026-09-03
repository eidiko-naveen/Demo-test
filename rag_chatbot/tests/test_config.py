import pytest

from config.settings import Settings


def test_groq_requires_key():
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="groq").validate_runtime()


def test_invalid_provider_is_rejected():
    with pytest.raises(ValueError):
        Settings(llm_provider="unknown").validate_runtime()


def test_groq_model_is_configurable():
    settings = Settings(llm_provider="groq", groq_api_key="test", groq_model="custom")
    settings.validate_runtime()
    assert settings.model_name == "custom"