import asyncio
import logging
import os
from typing import Any

from qdrant_client import QdrantClient, models

from app.config.settings import Settings
from app.utils.exceptions import VectorStoreError

logger = logging.getLogger("enterprise_rag")

_shared_fallback_client: QdrantClient | None = None


def get_shared_fallback_client() -> QdrantClient:
    """Return one shared in-memory Qdrant client for development only."""
    global _shared_fallback_client

    if _shared_fallback_client is None:
        _shared_fallback_client = QdrantClient(location=":memory:")

    return _shared_fallback_client


class QdrantVectorStore:
    """Qdrant vector-store wrapper."""

    def __init__(self, settings: Settings):
        self.collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension
        self._production = self._is_production(settings)
        self._qdrant_url = self._resolve_qdrant_url(settings)
        self._client = self._init_client(settings)

    @staticmethod
    def _is_production(settings: Settings) -> bool:
        """Return True when running in a production or Kubernetes environment."""
        configured_environment = settings.app_env.lower().strip()
        return configured_environment in {
            "production",
            "prod",
            "docker",
            "container",
        } or bool(os.getenv("KUBERNETES_SERVICE_HOST"))

    def _resolve_qdrant_url(self, settings: Settings) -> str:
        """Resolve the correct Qdrant endpoint for the runtime environment."""
        url = (settings.qdrant_url or "").strip()

        if not url:
            if self._production:
                return "http://qdrant:6333"
            return ""

        if self._production and (
            url.startswith("http://localhost")
            or url.startswith("http://127.0.0.1")
            or url.startswith("https://localhost")
            or url.startswith("https://127.0.0.1")
        ):
            return "http://qdrant:6333"

        return url

    def _init_client(self, settings: Settings) -> QdrantClient:
        """Create the remote Qdrant client or a development-only fallback."""
        if not self._qdrant_url:
            if self._production:
                raise VectorStoreError(
                    "Qdrant URL is not configured for the production environment."
                )

            logger.info(
                "Qdrant URL is not configured; using in-memory vector store for development."
            )
            return get_shared_fallback_client()

        try:
            client = QdrantClient(
                url=self._qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=5.0,
                check_compatibility=False,
            )
            client.get_collections()
            logger.info("Connected to Qdrant successfully at %s", self._qdrant_url)
            return client
        except Exception as exc:
            if self._production:
                logger.error("Qdrant is unavailable at %s: %s", self._qdrant_url, exc)
                raise VectorStoreError(
                    f"Unable to connect to Qdrant at {self._qdrant_url}"
                ) from exc

            logger.info(
                "Remote Qdrant at %s is unavailable; using in-memory vector store for development.",
                self._qdrant_url,
            )
            return get_shared_fallback_client()

    async def ensure_collection(self) -> None:
        """Create the configured collection when it does not exist."""
        try:
            exists = await asyncio.to_thread(
                self._client.collection_exists,
                self.collection,
            )

            if not exists:
                await asyncio.to_thread(
                    self._client.create_collection,
                    collection_name=self.collection,
                    vectors_config=models.VectorParams(
                        size=self._dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
        except Exception as exc:
            raise VectorStoreError("Unable to initialize Qdrant collection") from exc

    async def upsert(
        self,
        point_ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        """Insert or update vectors in Qdrant."""
        if not len(point_ids) == len(vectors) == len(payloads):
            raise ValueError(
                "point_ids, vectors, and payloads must have the same length"
            )

        points = [
            models.PointStruct(id=point_id, vector=vector, payload=payload)
            for point_id, vector, payload in zip(
                point_ids,
                vectors,
                payloads,
                strict=True,
            )
        ]

        try:
            await asyncio.to_thread(
                self._client.upsert,
                collection_name=self.collection,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Unable to write vectors to Qdrant") from exc

    async def similarity_search(
        self,
        vector: list[float],
        *,
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search Qdrant for the most similar vectors."""
        try:
            exists = await asyncio.to_thread(
                self._client.collection_exists,
                self.collection,
            )

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
        """Check whether the configured Qdrant service is reachable."""
        try:
            await asyncio.to_thread(self._client.get_collections)
            return True
        except Exception:
            return False
