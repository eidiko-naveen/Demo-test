import logging

from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import app, create_app
from app.schemas.chat import ChatRequest
from app.schemas.response import AgentResponse
from app.services.chat_service import ChatService


class FakeAgent:
    def __init__(self) -> None:
        self.kwargs = {}

    async def run(self, query: str, **kwargs):
        self.kwargs = kwargs
        return AgentResponse(answer="ok", agent_type="research", memory_mode="none")


def test_metadata_routes_are_available() -> None:
    client = TestClient(app)

    assert client.get("/api/v1/agents").json()["agents"]
    modes = [m["id"] for m in client.get("/api/v1/memory/modes").json()["modes"]]
    assert "langchain" in modes
    assert "langgraph" in modes
    assert "none" in modes


def test_app_builds_chat_service_when_llm_is_configured(monkeypatch) -> None:
    class FakeLLM:
        async def ainvoke(self, messages):
            return "ok"

    class FakeEmbeddings:
        def embed_documents(self, texts):
            return [[0.1, 0.2] for _ in texts]

        def embed_query(self, text):
            return [0.1, 0.2]

    class FakeVectorStore:
        async def ensure_collection(self) -> None: return None

        async def upsert(self, point_ids, vectors, payloads) -> None: return None

        async def similarity_search(self, vector, *, top_k, score_threshold=None):
            return [{"score": 0.9, "payload": {"document_name": "policy.txt"}}]

        async def health_check(self) -> bool:
            return True

    class FakeAgent:
        async def run(self, query: str, **kwargs):
            return AgentResponse(answer="ok", agent_type="rag", memory_mode="none")

    monkeypatch.setattr("app.main.LLMFactory.create", lambda settings: FakeLLM())
    monkeypatch.setattr("app.main.EmbeddingFactory.create", lambda settings: FakeEmbeddings())
    monkeypatch.setattr("app.main.QdrantVectorStore", lambda settings: FakeVectorStore())
    monkeypatch.setattr("app.main.AgentFactory.create", lambda *args, **kwargs: FakeAgent())

    application = create_app(
        Settings(
            groq_api_key="test-key",
            qdrant_url="http://localhost:6333",
            qdrant_api_key=None,
            qdrant_collection="enterprise_documents",
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )

    assert application.state.chat_service is not None


def test_app_logs_startup_and_shutdown(caplog) -> None:
    caplog.set_level(logging.INFO, logger="enterprise_rag")

    with TestClient(app):
        pass

    assert "Application startup complete" in caplog.text
    assert "Application shutdown complete" in caplog.text


def test_chat_reports_unconfigured_service_safely() -> None:
    unconfigured_app = create_app(Settings(groq_api_key=""))
    response = TestClient(unconfigured_app).post("/api/v1/chat", json={"query": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Chat service is not configured"


def test_upload_rejects_unsupported_file_type() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.exe", b"not-a-valid-doc", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_health_sets_request_id_header() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")


def test_document_upload_uses_document_service() -> None:
    class FakeDocumentService:
        def __init__(self) -> None:
            self.calls = []

        async def ingest_file(self, path, **kwargs):
            self.calls.append({"path": str(path), **kwargs})
            return type("Result", (), {"chunk_count": 1, "document_id": "doc-123"})()

    fake_service = FakeDocumentService()
    app.state.document_service = fake_service

    response = TestClient(app).post(
        "/api/v1/documents/upload",
        files={"file": ("policy.txt", b"Company policy content", "text/plain")},
        headers={"X-User-Id": "user-42", "X-Tenant-Id": "tenant-42"},
    )

    assert response.status_code == 200
    assert fake_service.calls
    assert fake_service.calls[0]["user_id"] == "user-42"
    assert fake_service.calls[0]["tenant_id"] == "tenant-42"


def test_document_routes_list_and_get_current_user_documents() -> None:
    class FakeDocumentService:
        async def list_documents(self, *, tenant_id: str, user_id: str):
            return [
                {
                    "document_id": "doc-123",
                    "document_name": "policy.txt",
                    "document_type": "txt",
                    "checksum": "abc",
                    "current_version": 1,
                    "metadata_json": {"source": "upload"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ]

        async def get_document(self, *, tenant_id: str, user_id: str, document_id: str):
            if document_id != "doc-123":
                return None
            return {
                "document_id": "doc-123",
                "document_name": "policy.txt",
                "document_type": "txt",
                "checksum": "abc",
                "current_version": 1,
                "metadata_json": {"source": "upload"},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }

    app.state.document_service = FakeDocumentService()

    list_response = TestClient(app).get(
        "/api/v1/documents",
        headers={"X-User-Id": "user-42", "X-Tenant-Id": "tenant-42"},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["document_name"] == "policy.txt"

    detail_response = TestClient(app).get(
        "/api/v1/documents/doc-123",
        headers={"X-User-Id": "user-42", "X-Tenant-Id": "tenant-42"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["document_id"] == "doc-123"


def test_document_delete_route_for_current_user() -> None:
    class FakeDocumentService:
        def __init__(self) -> None:
            self.deleted = []

        async def delete_document(self, *, tenant_id: str, user_id: str, document_id: str):
            self.deleted.append({"tenant_id": tenant_id, "user_id": user_id, "document_id": document_id})
            return True

    app.state.document_service = FakeDocumentService()

    response = TestClient(app).delete(
        "/api/v1/documents/doc-123",
        headers={"X-User-Id": "user-42", "X-Tenant-Id": "tenant-42"},
    )

    assert response.status_code == 204
    assert app.state.document_service.deleted == [
        {"tenant_id": "tenant-42", "user_id": "user-42", "document_id": "doc-123"}
    ]


def test_chat_service_dispatches_research_arguments() -> None:
    agent = FakeAgent()
    service = ChatService(lambda _: agent)

    import asyncio

    asyncio.run(service.chat(ChatRequest(query="latest practice", agent_type="research", top_k=7)))

    assert agent.kwargs["limit"] == 7
    assert "score_threshold" not in agent.kwargs
