import asyncio
from typing import Any

from app.config.settings import Settings
from app.rag.pipeline import IngestionPipeline


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class FakeVectorStore:
    def __init__(self) -> None:
        self.points: list[tuple[str, list[float], dict[str, Any]]] = []
        self.collection_ready = False

    async def ensure_collection(self) -> None:
        self.collection_ready = True

    async def upsert(
        self, point_ids: list[str], vectors: list[list[float]], payloads: list[dict[str, Any]]
    ) -> None:
        self.points.extend(zip(point_ids, vectors, payloads, strict=True))


def test_ingestion_adds_stable_metadata(tmp_path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("Company policy content", encoding="utf-8")
    vector_store = FakeVectorStore()
    pipeline = IngestionPipeline(Settings(), FakeEmbeddings(), vector_store)

    result = asyncio.run(pipeline.ingest(path, tenant_id="tenant-a", user_id="user-a"))

    assert result.chunk_count == 1
    assert vector_store.collection_ready is True
    assert vector_store.points[0][2]["tenant_id"] == "tenant-a"
    assert vector_store.points[0][2]["document_name"] == "policy.txt"


def test_document_service_ingests_uploaded_file(tmp_path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("Company policy content", encoding="utf-8")

    vector_store = FakeVectorStore()
    pipeline = IngestionPipeline(Settings(), FakeEmbeddings(), vector_store)

    from app.services.document_service import DocumentService

    service = DocumentService(pipeline=pipeline)
    result = asyncio.run(service.ingest_file(path, tenant_id="tenant-a", user_id="user-a"))

    assert result.chunk_count == 1
    assert result.document_id
    assert vector_store.points


def test_enterprise_retriever_returns_indexed_document_payloads() -> None:
    class RetrievalVectorStore:
        async def similarity_search(self, vector, *, top_k, score_threshold=None):
            return [
                {
                    "score": 0.98,
                    "payload": {
                        "document_name": "policy.txt",
                        "source": "https://example.com/policy",
                        "tenant_id": "tenant-a",
                        "user_id": "user-a",
                    },
                }
            ]

    from app.rag.retriever import EnterpriseRetriever

    retriever = EnterpriseRetriever(FakeEmbeddings(), RetrievalVectorStore())
    results = asyncio.run(retriever.retrieve("policy", top_k=3))

    assert len(results) == 1
    assert results[0]["payload"]["document_name"] == "policy.txt"
    assert results[0]["score"] == 0.98
