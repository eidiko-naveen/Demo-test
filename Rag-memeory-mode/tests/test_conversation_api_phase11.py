from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.v1.conversations import get_conversation_service
from app.main import app
from app.schemas.conversation import ConversationResponse


class FakeConversationService:
    async def list_for_current_user(self):
        return []

    async def create_for_current_user(self, payload):
        now = datetime.now(timezone.utc)
        return ConversationResponse(
            id="conversation-1",
            title=payload.title,
            agent_type=payload.agent_type,
            memory_mode=payload.memory_mode,
            created_at=now,
            updated_at=now,
        )

    async def get_for_current_user(self, conversation_id):
        if conversation_id == "missing":
            return None
        return ConversationResponse(
            id=conversation_id,
            title="Project",
            agent_type="rag",
            memory_mode="buffer",
        )

    async def archive(self, conversation_id):
        return conversation_id != "missing"


def test_conversation_routes_use_injected_service() -> None:
    app.dependency_overrides[get_conversation_service] = FakeConversationService
    client = TestClient(app)
    try:
        assert client.get("/api/v1/conversations").status_code == 200
        created = client.post(
            "/api/v1/conversations", json={"title": "Project", "memory_mode": "buffer"}
        )
        assert created.status_code == 200
        assert created.json()["id"] == "conversation-1"
        assert client.get("/api/v1/conversations/conversation-1").status_code == 200
        assert client.get("/api/v1/conversations/missing").status_code == 404
        assert client.delete("/api/v1/conversations/conversation-1").status_code == 204
        assert client.delete("/api/v1/conversations/missing").status_code == 404
    finally:
        app.dependency_overrides.pop(get_conversation_service, None)
