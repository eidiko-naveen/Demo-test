from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] in {"healthy", "degraded"}
    assert response.json()["services"]["application"] == "healthy"


def test_readiness_reports_runtime_state() -> None:
    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] in {"ready", "not_ready"}


def test_production_defaults_use_container_service_hosts() -> None:
    settings = Settings(app_env="production")

    assert settings.qdrant_url == "http://qdrant:6333"
    assert settings.database_url.endswith("@postgres:5432/enterprise_rag")


def test_kubernetes_runtime_treats_localhost_qdrant_as_production(monkeypatch) -> None:
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    settings = Settings(app_env="development", qdrant_url="http://localhost:6333")

    from app.vectorstore.qdrant import QdrantVectorStore

    store = object.__new__(QdrantVectorStore)
    store._production = store._is_production(settings)

    assert store._production is True
    assert store._resolve_qdrant_url(settings) == "http://qdrant:6333"


def test_huggingface_cache_uses_writable_local_directory(monkeypatch, tmp_path) -> None:
    target_dir = tmp_path / ".cache" / "huggingface"
    monkeypatch.setenv("HF_HOME", str(target_dir))

    from app.rag.embeddings import _resolve_huggingface_cache_dir

    resolved = _resolve_huggingface_cache_dir()

    assert resolved == str(target_dir)
    assert target_dir.exists()
    assert target_dir.is_dir()
