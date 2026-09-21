from typing import Any

from app.rag.embeddings import EmbeddingProvider
from app.vectorstore.base import VectorStore


class EnterpriseRetriever:
    def __init__(self, embeddings: EmbeddingProvider, vector_store: VectorStore):
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def retrieve(
        self, query: str, *, top_k: int = 5, score_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        vector = self.embeddings.embed_query(query)
        return await self.vector_store.similarity_search(
            vector, top_k=top_k, score_threshold=score_threshold
        )
