"""
Centralized app settings, loaded from environment variables / .env file.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (Groq) ---
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Database ---
    database_url: str

    # --- App ---
    port: int = 8000
    default_memory_mode: str = "hybrid"
    buffer_window_size: int = 6
    log_level: str = "INFO"

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384


@lru_cache
def get_settings() -> Settings:
    return Settings()