from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database import repository


def isolated_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_sessions_and_messages_are_isolated_by_identity():
    sessions = isolated_db()
    with patch.object(repository, "db_session", side_effect=lambda: sessions()):
        repository.create_session("user-a-session", user_id="user-a", tenant_id="tenant-a")
        repository.create_session("user-b-session", user_id="user-b", tenant_id="tenant-b")
        repository.add_message("user-a-session", "user", "private-a", "user-a", "tenant-a")
        repository.add_message("user-b-session", "user", "private-b", "user-b", "tenant-b")

        assert [item.id for item in repository.list_sessions(user_id="user-a", tenant_id="tenant-a")] == ["user-a-session"]
        assert [item.content for item in repository.get_messages("user-a-session", user_id="user-a", tenant_id="tenant-a")] == ["private-a"]
        assert repository.get_messages("user-b-session", user_id="user-a", tenant_id="tenant-a") == []

        with pytest.raises(PermissionError):
            repository.add_message("user-b-session", "user", "overwrite", "user-a", "tenant-a")
        repository.delete_session("user-b-session", user_id="user-a", tenant_id="tenant-a")
        assert [item.id for item in repository.list_sessions(user_id="user-b", tenant_id="tenant-b")] == ["user-b-session"]


def test_enterprise_identity_requires_explicit_trusted_provider():
    from auth import identity

    settings = SimpleNamespace(auth_mode="enterprise")
    with patch.object(identity, "get_settings", return_value=settings):
        identity._authentication_provider = None
        with pytest.raises(RuntimeError, match="provider is not configured"):
            identity.get_current_identity()

        provider = SimpleNamespace(
            authenticate=lambda: identity.UserIdentity("user-a", "tenant-a")
        )
        identity.configure_authentication_provider(provider)
        assert identity.get_current_identity() == identity.UserIdentity("user-a", "tenant-a")
        identity._authentication_provider = None


def test_retrieval_always_supplies_both_identity_filters():
    captured = {}

    class Retriever:
        def retrieve(self, question):
            return []

    class Index:
        def as_retriever(self, **kwargs):
            captured.update(kwargs)
            return Retriever()

    settings = SimpleNamespace(top_k=5, relevance_threshold=0.3)
    with patch("rag.engine.get_settings", return_value=settings), patch("rag.engine.has_collection", return_value=True), patch("rag.engine.get_index", return_value=Index()):
        from rag.engine import retrieve_evidence
        result = retrieve_evidence("question", user_id="user-a", tenant_id="tenant-a")

    assert result["sources"] == []
    filters = captured["filters"].filters
    assert {(item.key, item.value) for item in filters} == {("user_id", "user-a"), ("tenant_id", "tenant-a")}


def test_upload_validation_rejects_fake_pdf_and_archive_bomb():
    from utils.security import validate_upload

    with pytest.raises(ValueError):
        validate_upload("file.pdf", 8, 1, b"not-a-pdf")

    archive_settings = SimpleNamespace(max_archive_members=1, max_archive_uncompressed_mb=1)
    with pytest.raises(ValueError):
        validate_upload("file.docx", 4, 1, b"PK\x03\x04", archive_settings)
