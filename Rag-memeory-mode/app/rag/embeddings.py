from typing import Protocol

from app.config.settings import Settings


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HuggingFaceEmbeddingProvider:
    def __init__(self, model_name: str):
        from langchain_huggingface import HuggingFaceEmbeddings

        self._embeddings = HuggingFaceEmbeddings(model_name=model_name)

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
