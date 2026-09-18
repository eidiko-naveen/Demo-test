from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, EntityMixin, UserOwnedMixin


class User(EntityMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Conversation(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "conversations"

    title: Mapped[str] = mapped_column(String(255))
    agent_type: Mapped[str] = mapped_column(String(50), default="rag")
    memory_mode: Mapped[str] = mapped_column(String(50), default="none")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Message(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Document(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(255), index=True)
    document_name: Mapped[str] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DocumentVersion(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Memory(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "memories"

    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(50), index=True)
    memory_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditLog(EntityMixin, UserOwnedMixin, Base):
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
