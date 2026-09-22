import os
from pathlib import Path
from typing import Protocol

from app.config.settings import Settings


def _resolve_huggingface_cache_dir() -> str:
    env_cache_dir = os.getenv("HF_HOME")
    if env_cache_dir:
        cache_dir = Path(env_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir)

    candidate_dirs = [
        Path.home() / ".cache" / "huggingface",
        Path(__file__).resolve().parents[2] / ".cache" / "huggingface",
    ]

    for cache_dir in candidate_dirs:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["HF_HOME"] = str(cache_dir)
            return str(cache_dir)
        except OSError:
            continue

    fallback_dir = Path("/tmp") / ".cache" / "huggingface"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(fallback_dir)
    return str(fallback_dir)


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HuggingFaceEmbeddingProvider:
    def __init__(self, model_name: str):
        from langchain_huggingface import HuggingFaceEmbeddings

        cache_dir = _resolve_huggingface_cache_dir()
        self._embeddings = HuggingFaceEmbeddings(model_name=model_name, cache_folder=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)


class EmbeddingFactory:
    @staticmethod
    def create(settings: Settings) -> EmbeddingProvider:
        if settings.embedding_provider.lower() == "huggingface":
            return HuggingFaceEmbeddingProvider(settings.embedding_model)
        raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
