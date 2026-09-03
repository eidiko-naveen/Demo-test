"""
Document ingestion: takes raw text, splits it into overlapping chunks,
embeds each chunk, and stores it in the `documents` table for later
retrieval by rag/retriever.py. This is what populates the RAG knowledge
base — separate from conversation memory, which lives in conversation_turns.
"""
import structlog

from src.db.models import Document
from src.db.session import get_db_session
from src.rag.retriever import embed_text

logger = structlog.get_logger()

CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 150    # overlap so context isn't lost at chunk boundaries


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Simple sliding-window character-based chunker. Not sentence-aware, but
    fast, dependency-free, and good enough for a demo knowledge base — a
    production system would swap this for a sentence/paragraph-aware
    splitter (e.g. langchain's RecursiveCharacterTextSplitter) without
    touching anything else in this file's contract (still takes text, still
    returns list[str]).
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


async def ingest_document(source: str, text: str, metadata: dict | None = None) -> int:
    """
    Chunks `text`, embeds each chunk, stores in `documents`.
    Returns the number of chunks stored.
    """
    chunks = chunk_text(text)
    metadata = metadata or {}

    async with get_db_session() as db:
        for chunk in chunks:
            embedding = await embed_text(chunk)
            db.add(Document(source=source, chunk_text=chunk, embedding=embedding, doc_metadata=metadata))

    logger.info("document_ingested", source=source, chunk_count=len(chunks))
    return len(chunks)