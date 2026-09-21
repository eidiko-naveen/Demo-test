from fastapi import APIRouter

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents() -> dict[str, list[dict[str, str]]]:
    return {
        "agents": [
            {"id": "rag", "name": "RAG Agent"},
            {"id": "research", "name": "Research Agent"},
            {"id": "hybrid", "name": "Hybrid Agent"},
        ]
    }
