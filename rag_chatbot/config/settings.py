from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str | None = None
    llm_provider: str = "groq"
    groq_model: str = "qwen/qwen3.8-27b"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    database_url: str = (
        f"sqlite:///{BASE_DIR / 'storage' / 'chatbot.db'}"
    )

    qdrant_path: str = str(BASE_DIR / "qdrant_storage")
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "enterprise_rag"

    data_dir: str = str(BASE_DIR / "data")

    auth_mode: str = "development"
    dev_user_id: str = "development-user"
    dev_tenant_id: str = "development-tenant"

    top_k: int = 5
    relevance_threshold: float = 0.35
    chunk_size: int = 800
    chunk_overlap: int = 120

    max_history_messages: int = 50
    memory_window_size: int = 6
    memory_context_chars: int = 12000
    summary_trigger_messages: int = 12
    memory_retention_enabled: bool = False
    memory_retention_days: int = 30

    upload_max_size_mb: int = 25
    upload_max_files: int = 10
    upload_max_total_size_mb: int = 100
    max_extracted_chars: int = 2_000_000
    max_archive_members: int = 2_000
    max_archive_uncompressed_mb: int = 100
    max_question_chars: int = 8_000
    max_concurrent_requests: int = 8
    external_search_provider: str | None = None
    external_search_timeout: int = 10
    external_search_max_results: int = 5
    external_search_country: str | None = None

    @property
    def model_name(self) -> str:
        return self.groq_model

    @property
    def is_development(self) -> bool:
        return self.auth_mode == "development"

    def validate_runtime(self) -> None:
        if self.llm_provider != "groq":
            raise ValueError("LLM_PROVIDER must be groq")
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        if self.llm_temperature < 0 or self.llm_temperature > 1:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 1")
        if self.llm_max_tokens < 1 or self.top_k < 1 or self.relevance_threshold < 0 or self.relevance_threshold > 1:
            raise ValueError("LLM_MAX_TOKENS and TOP_K must be positive")
        if self.chunk_size < 1 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_SIZE and CHUNK_OVERLAP are invalid")
        if self.max_history_messages < 1 or self.memory_window_size < 1 or self.memory_context_chars < 1:
            raise ValueError("Memory limits must be positive")
        if self.upload_max_size_mb < 1:
            raise ValueError("UPLOAD_MAX_SIZE_MB must be positive")
        if min(self.upload_max_files, self.upload_max_total_size_mb, self.max_extracted_chars, self.max_archive_members, self.max_archive_uncompressed_mb, self.max_question_chars, self.max_concurrent_requests) < 1:
            raise ValueError("Resource limits must be positive")
        if self.auth_mode not in {"development", "enterprise"}:
            raise ValueError("AUTH_MODE must be development or enterprise")
        if self.auth_mode == "enterprise":
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Enterprise mode requires a PostgreSQL DATABASE_URL")
            if not self.qdrant_url or not self.qdrant_api_key:
                raise ValueError("Enterprise mode requires authenticated QDRANT_URL and QDRANT_API_KEY")

    langfuse_enabled: bool = False
    langfuse_capture_content: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices(
            "LANGFUSE_HOST",
            "LANGFUSE_BASE_URL",
            "langfuse_host",
            "langfuse_base_url",
        ),
    )

    def ensure_directories(self) -> None:

        Path(self.data_dir).mkdir(
            parents=True,
            exist_ok=True,
        )

        Path(self.qdrant_path).mkdir(
            parents=True,
            exist_ok=True,
        )

        (
            BASE_DIR / "storage"
        ).mkdir(
            parents=True,
            exist_ok=True,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:

    settings = Settings()

    settings.ensure_directories()

    return settings