import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.documents import DocumentRepository
from app.database.session import get_session
from app.schemas.document import DocumentRecordResponse, DocumentUploadResponse
from app.security.auth import UserContext, get_current_user
from app.services.document_service import DocumentService
from app.utils.exceptions import DocumentIngestionError, VectorStoreError

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".json"}


def _as_document_response(payload: dict) -> DocumentRecordResponse:
    normalized = dict(payload)
    normalized.setdefault("id", normalized.get("document_id"))
    return DocumentRecordResponse(**normalized)


def _validate_upload_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="A document filename is required")

    normalized_name = os.path.basename(filename)
    extension = Path(normalized_name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {normalized_name}. Allowed types: {allowed}",
        )
    return normalized_name


def get_document_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DocumentService:
    service = getattr(request.app.state, "document_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Document service is not configured")
    service.repository = DocumentRepository(session)
    return service


@router.get("", response_model=list[DocumentRecordResponse])
async def list_documents(
    service: DocumentService = Depends(get_document_service),
    context: UserContext = Depends(get_current_user),
) -> list[DocumentRecordResponse]:
    documents = await service.list_documents(tenant_id=context.tenant_id, user_id=context.user_id)
    return [_as_document_response(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentRecordResponse)
async def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
    context: UserContext = Depends(get_current_user),
) -> DocumentRecordResponse:
    document = await service.get_document(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _as_document_response(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
    context: UserContext = Depends(get_current_user),
) -> Response:
    if not await service.delete_document(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        document_id=document_id,
    ):
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    context: UserContext = Depends(get_current_user),
) -> DocumentUploadResponse:
    settings = request.app.state.settings
    service = getattr(request.app.state, "document_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Document service is not configured")
    service.repository = DocumentRepository(session)

    safe_name = _validate_upload_filename(file.filename)
    content = await file.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds the configured upload size limit")

    with NamedTemporaryFile(suffix=Path(safe_name).suffix, delete=False) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        result = await service.ingest_file(
            temp_path,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            metadata={"document_name": safe_name},
        )
    except DocumentIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return DocumentUploadResponse(
        document_name=safe_name,
        status="accepted" if result else "failed",
        message=(
            f"Upload ingested successfully ({result.chunk_count} chunks)"
            if result
            else "Upload failed during ingestion processing"
        ),
    )
