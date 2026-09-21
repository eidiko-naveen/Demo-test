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
