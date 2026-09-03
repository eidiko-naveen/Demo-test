"""
Embedding generation + similarity search against the `documents` table.
Also exposes embed_text() as a shared utility — every memory mode that
stores an embedding (Buffer, Vector, Persistent, Hybrid) imports it from
here rather than duplicating embedding logic.
"""
from functools import lru_cache

import structlog
from fastembed import TextEmbedding
from sqlalchemy import select

from src.config import get_settings
from src.db.models import Document
from src.db.session import get_db_session

logger = structlog.get_logger()


@lru_cache
def _get_embedder() -> TextEmbedding:
    """
    Cached singleton — fastembed loads an ONNX model into memory on first
    use (a few hundred MB); we do NOT want to reload it per request.
    """
    settings = get_settings()
    logger.info("loading_embedding_model", model=settings.embedding_model)
    return TextEmbedding(model_name=settings.embedding_model)


async def embed_text(text: str) -> list[float]:
    """
    fastembed's .embed() is a sync generator under the hood (CPU-bound ONNX
    inference) — there's no natural async version, so we call it directly.
    For this project's scale (single-user demo, not high concurrency) this
    is fine; a high-throughput production system would offload this to a
    thread pool via asyncio.to_thread().
    """
    embedder = _get_embedder()
    embeddings = list(embedder.embed([text]))
    return embeddings[0].tolist()


async def retrieve_relevant_chunks(query: str, top_k: int = 4, max_distance: float = 0.6) -> list[str]:
    """
    max_distance filters out chunks that aren't actually relevant — cosine
    distance ranges 0 (identical) to 2 (opposite); 0.6 is a reasonable cutoff
    so unrelated queries (like "2+2") don't drag in random document text.
    """
    query_embedding = await embed_text(query)

    async with get_db_session() as db:
        result = await db.execute(
            select(Document.chunk_text, Document.embedding.cosine_distance(query_embedding).label("distance"))
            .order_by("distance")
            .limit(top_k)
        )
        rows = result.all()
        return [row.chunk_text for row in rows if row.distance <= max_distance]