import asyncio
import logging
from typing import Any

from qdrant_client import QdrantClient, models

from app.config.settings import Settings
from app.utils.exceptions import VectorStoreError

logger = logging.getLogger("enterprise_rag")

_shared_fallback_client: QdrantClient | None = None


def get_shared_fallback_client() -> QdrantClient:
    global _shared_fallback_client
    if _shared_fallback_client is None:
        _shared_fallback_client = QdrantClient(location=":memory:")
    return _shared_fallback_client


class QdrantVectorStore:
    def __init__(self, settings: Settings):
        self.collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension
        self._client = self._init_client(settings)

    @staticmethod
    def _init_client(settings: Settings) -> QdrantClient:
        if settings.qdrant_url:
            try:
                client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=2.0,
                    check_compatibility=False,
                )
                client.get_collections()
                return client
            except Exception as exc:
                logger.warning(
                    "Remote Qdrant at %s unreachable (%s); using in-memory vector store fallback.",
                    settings.qdrant_url,
                    exc,
                )
        return get_shared_fallback_client()

    async def ensure_collection(self) -> None:
        try:
            exists = await asyncio.to_thread(self._client.collection_exists, self.collection)
            if not exists:
                await asyncio.to_thread(
                    self._client.create_collection,
                    collection_name=self.collection,
                    vectors_config=models.VectorParams(
                        size=self._dimension, distance=models.Distance.COSINE
                    ),
                )
        except Exception as exc:
            raise VectorStoreError("Unable to initialize Qdrant collection") from exc

    async def upsert(
        self, point_ids: list[str], vectors: list[list[float]], payloads: list[dict[str, Any]]
    ) -> None:
        if not len(point_ids) == len(vectors) == len(payloads):
            raise ValueError("point_ids, vectors, and payloads must have the same length")
        points = [
            models.PointStruct(id=point_id, vector=vector, payload=payload)
            for point_id, vector, payload in zip(point_ids, vectors, payloads, strict=True)
        ]
        try:
            await asyncio.to_thread(
                self._client.upsert, collection_name=self.collection, points=points, wait=True
            )
        except Exception as exc:
            raise VectorStoreError("Unable to write vectors to Qdrant") from exc

    async def similarity_search(
        self, vector: list[float], *, top_k: int, score_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        try:
            exists = await asyncio.to_thread(self._client.collection_exists, self.collection)
            if not exists:
                return []
            response = await asyncio.to_thread(
                self._client.query_points,
                collection_name=self.collection,
                query=vector,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [
                {"score": point.score, "payload": point.payload or {}}
                for point in response.points
            ]
        except Exception as exc:
            raise VectorStoreError("Unable to search Qdrant") from exc

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._client.get_collections)
            return True
        except Exception:
            return False
