from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, DocumentVersion


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        document_id: str,
        document_name: str,
        document_type: str,
        checksum: str,
        current_version: int,
        metadata: dict | None = None,
        source: str | None = None,
    ) -> Document:
        document = Document(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
            document_name=document_name,
            document_type=document_type,
            source=source,
            current_version=current_version,
            checksum=checksum,
            metadata_json=metadata or {},
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def list(self, *, tenant_id: str, user_id: str) -> Sequence[Document]:
        statement = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.user_id == user_id,
        )
        return (await self.session.scalars(statement)).all()

    async def get_by_document_id(
        self, *, tenant_id: str, user_id: str, document_id: str
    ) -> Document | None:
        statement = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.user_id == user_id,
            Document.document_id == document_id,
        )
        return await self.session.scalar(statement)

    async def record_ingestion(
        self,
        *,
        tenant_id: str,
        user_id: str,
        document_id: str,
        document_name: str,
        document_type: str,
        checksum: str,
        version: int,
        metadata: dict | None = None,
        source: str | None = None,
        chunk_count: int = 0,
    ) -> Document:
        document = await self.get_by_document_id(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
        )
        if document is None:
            document = await self.create(
                tenant_id=tenant_id,
                user_id=user_id,
                document_id=document_id,
                document_name=document_name,
                document_type=document_type,
                checksum=checksum,
                current_version=version,
                metadata=metadata,
                source=source,
            )
        else:
            document.document_name = document_name
            document.document_type = document_type
            document.checksum = checksum
            document.current_version = max(document.current_version, version)
            document.source = source or document.source
            if metadata:
                merged = dict(document.metadata_json)
                merged.update(metadata)
                document.metadata_json = merged
            await self.session.commit()
            await self.session.refresh(document)

        version_record = DocumentVersion(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
            version=version,
            checksum=checksum,
            ingestion_timestamp=document.updated_at or document.created_at,
            chunk_count=chunk_count,
            metadata_json=metadata or {},
        )
        self.session.add(version_record)
        await self.session.commit()
        return document

    async def delete(self, *, tenant_id: str, user_id: str, document_id: str) -> bool:
        statement = delete(Document).where(
            Document.tenant_id == tenant_id,
            Document.user_id == user_id,
            Document.document_id == document_id,
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return result.rowcount > 0
