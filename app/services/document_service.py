from pathlib import Path
from typing import Any

from app.database.repositories.documents import DocumentRepository
from app.rag.embeddings import EmbeddingFactory
from app.rag.pipeline import IngestionPipeline, IngestionResult
from app.utils.exceptions import DocumentIngestionError
from app.vectorstore.qdrant import QdrantVectorStore


class DocumentService:
    """Application service for enterprise document ingestion."""

    def __init__(self, *, pipeline: IngestionPipeline | None = None, repository: DocumentRepository | None = None):
        self.pipeline = pipeline
        self.repository = repository

    @classmethod
    def from_settings(cls, settings: Any) -> "DocumentService":
        embeddings = EmbeddingFactory.create(settings)
        vector_store = QdrantVectorStore(settings)
        pipeline = IngestionPipeline(settings=settings, embeddings=embeddings, vector_store=vector_store)
        return cls(pipeline=pipeline)

    async def ingest_file(
        self,
        path: Path | str,
        *,
        tenant_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        version: int = 1,
    ) -> IngestionResult:
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            raise DocumentIngestionError("Document file does not exist")
        if self.pipeline is None:
            raise DocumentIngestionError("Document ingestion pipeline is not configured")

        result = await self.pipeline.ingest(
            file_path,
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata,
            version=version,
        )

        if self.repository is not None:
            document_name = str((metadata or {}).get("document_name") or file_path.name)
            await self.repository.record_ingestion(
                tenant_id=tenant_id,
                user_id=user_id,
                document_id=result.document_id,
                document_name=document_name,
                document_type=file_path.suffix.lower().lstrip("."),
                checksum=result.checksum,
                version=result.version,
                metadata={
                    **(metadata or {}),
                    "document_name": document_name,
                    "document_type": file_path.suffix.lower().lstrip("."),
                    "source": str(file_path),
                },
                source=str(file_path),
                chunk_count=result.chunk_count,
            )

        return result

    async def list_documents(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        if self.repository is None:
            return []

        documents = await self.repository.list(tenant_id=tenant_id, user_id=user_id)
        return [
            {
                "id": document.id,
                "document_id": document.document_id,
                "document_name": document.document_name,
                "document_type": document.document_type,
                "checksum": document.checksum,
                "current_version": document.current_version,
                "metadata_json": document.metadata_json,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
            }
            for document in documents
        ]

    async def get_document(
        self, *, tenant_id: str, user_id: str, document_id: str
    ) -> dict[str, Any] | None:
        if self.repository is None:
            return None

        document = await self.repository.get_by_document_id(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
        )
        if document is None:
            return None

        return {
            "id": document.id,
            "document_id": document.document_id,
            "document_name": document.document_name,
            "document_type": document.document_type,
            "checksum": document.checksum,
            "current_version": document.current_version,
            "metadata_json": document.metadata_json,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    async def delete_document(self, *, tenant_id: str, user_id: str, document_id: str) -> bool:
        if self.repository is None:
            return False
        return await self.repository.delete(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
        )
