from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.config.settings import Settings, get_settings
from app.database.session import get_engine
from app.vectorstore.qdrant import QdrantVectorStore

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]


async def _check_database() -> str:
    try:
        from app.database.session import get_session

        async for session in get_session():
            await session.execute(text("SELECT 1"))
            return "healthy"
        return "healthy"
    except Exception:
        return "unavailable"


async def _check_qdrant(settings: Settings) -> str:
    try:
        vector_store = QdrantVectorStore(settings)
        return "healthy" if await vector_store.health_check() else "unavailable"
    except Exception:
        return "unavailable"


@router.get("", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    services = {
        "application": "healthy",
        "database": "configured" if settings.database_url else "missing",
        "qdrant": "configured" if settings.qdrant_url else "missing",
        "llm": "configured" if settings.groq_api_key else "not_configured",
    }
    database_status = await _check_database() if settings.database_url else "missing"
    qdrant_status = await _check_qdrant(settings) if settings.qdrant_url else "missing"
    services["database"] = database_status
    services["qdrant"] = qdrant_status
    overall_status = "healthy" if all(value in {"healthy", "configured"} for value in (services["database"], services["qdrant"])) else "degraded"
    return HealthResponse(status=overall_status, services=services)


@router.get("/ready", response_model=HealthResponse)
async def readiness(settings: Settings = Depends(get_settings)) -> HealthResponse:
    response = await health(settings)
    ready_status = "ready" if response.status == "healthy" else "not_ready"
    return response.model_copy(update={"status": ready_status})
