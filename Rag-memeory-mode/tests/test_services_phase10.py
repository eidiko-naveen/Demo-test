import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config.settings import Settings
from app.schemas.conversation import ConversationCreateRequest
from app.security.auth import resolve_user_context
from app.services.conversation_service import ConversationService


class FakeConversationRepository:
    def __init__(self) -> None:
        self.create_kwargs = None
        self.list_kwargs = None

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id="conversation-1",
            title=kwargs["title"],
            agent_type=kwargs["agent_type"],
            memory_mode=kwargs["memory_mode"],
            archived=False,
            created_at=now,
            updated_at=now,
        )

    async def list(self, **kwargs):
        self.list_kwargs = kwargs
        return []


def test_mock_auth_uses_configured_identity() -> None:
    context = resolve_user_context(Settings(mock_user_id="u", mock_tenant_id="t"))

    assert context.user_id == "u"
    assert context.tenant_id == "t"


def test_required_auth_rejects_missing_identity() -> None:
    with pytest.raises(Exception):
        resolve_user_context(Settings(auth_mode="jwt"))


def test_conversation_service_scopes_repository_calls() -> None:
    repository = FakeConversationRepository()
    service = ConversationService(
        repository, resolve_user_context(Settings(mock_user_id="u", mock_tenant_id="t"))
    )

    response = asyncio.run(
        service.create_for_current_user(
            ConversationCreateRequest(title="Project", agent_type="rag", memory_mode="buffer")
        )
    )

    assert response.id == "conversation-1"
    assert repository.create_kwargs["tenant_id"] == "t"
    assert repository.create_kwargs["user_id"] == "u"
