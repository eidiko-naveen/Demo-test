import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.config.settings import Settings
from app.rag.chunking import TextChunker
from app.rag.embeddings import EmbeddingProvider
from app.rag.loaders import LoaderFactory
from app.rag.types import TextChunk
from app.utils.exceptions import DocumentIngestionError
from app.vectorstore.base import VectorStore


@dataclass(slots=True)
class IngestionResult:
    document_id: str
    checksum: str
    version: int
    chunk_count: int


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        chunker: TextChunker | None = None,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chunker = chunker or TextChunker()

    async def ingest(
        self,
        path: Path,
        *,
        tenant_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        version: int = 1,
    ) -> IngestionResult:
        self._validate_file(path)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        document_id = hashlib.sha256(f"{tenant_id}:{path.name}".encode()).hexdigest()
        loaded_documents = LoaderFactory.create(path).load(path)
        chunks = self.chunker.split(loaded_documents)
        if not chunks:
            raise DocumentIngestionError("The document contains no indexable text")

        ingestion_timestamp = datetime.now(timezone.utc).isoformat()
        base_metadata = {
            "document_id": document_id,
            "document_name": path.name,
            "document_type": path.suffix.lower().lstrip("."),
            "source": str(path),
            "version": version,
            "checksum": checksum,
            "ingestion_timestamp": ingestion_timestamp,
            "tenant_id": tenant_id,
            "user_id": user_id,
            **(metadata or {}),
        }
        payloads = [
            {"text": chunk.text, **base_metadata, **chunk.metadata, "chunk_id": index}
            for index, chunk in enumerate(chunks)
        ]
        vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
        point_ids = [
            str(uuid5(NAMESPACE_URL, f"{document_id}:{version}:{index}"))
            for index in range(len(chunks))
        ]
        await self.vector_store.ensure_collection()
        await self.vector_store.upsert(point_ids, vectors, payloads)
        return IngestionResult(document_id, checksum, version, len(chunks))

    def _validate_file(self, path: Path) -> None:
        if not path.is_file():
            raise DocumentIngestionError("Document file does not exist")
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if path.stat().st_size > max_bytes:
            raise DocumentIngestionError("Document exceeds the configured upload size limit")
