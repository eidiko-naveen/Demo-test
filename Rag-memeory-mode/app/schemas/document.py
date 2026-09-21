from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_name: str
    status: str
    message: str


class DocumentRecordResponse(BaseModel):
    id: str
    document_id: str
    document_name: str
    document_type: str
    checksum: str
    current_version: int
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
