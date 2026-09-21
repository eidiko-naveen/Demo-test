from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "Enterprise RAG Platform"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    auth_mode: str = "mock"
    mock_user_id: str = "development-user"
    mock_tenant_id: str = "development-tenant"

    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "enterprise_documents"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_rag"

    embedding_provider: str = "huggingface"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=1)

    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "enterprise-rag"

    memory_window_size: int = Field(default=10, ge=1, le=1000)
    max_upload_size_mb: int = Field(default=50, ge=1, le=1024)

    @model_validator(mode="after")
    def _apply_runtime_defaults(self):
        if self.app_env.lower() in {"production", "prod", "docker", "container"}:
            if self.qdrant_url.startswith("http://localhost") or self.qdrant_url.startswith("http://127.0.0.1"):
                self.qdrant_url = "http://qdrant:6333"
            if "localhost:5432" in self.database_url or self.database_url.startswith("postgresql+asyncpg://postgres:postgres@localhost"):
                self.database_url = "postgresql+asyncpg://postgres:postgres@postgres:5432/enterprise_rag"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
