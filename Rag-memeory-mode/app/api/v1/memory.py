from fastapi import APIRouter

from app.memory.factory import SUPPORTED_MEMORY_MODES


router = APIRouter(
    prefix="/memory",
    tags=["memory"],
)


MEMORY_MODE_METADATA = {
    "none": {
        "name": "Stateless",
        "description": "No conversation context is retained.",
        "scope": "none",
    },
    "short_term": {
        "name": "Short-term / Thread Memory",
        "description": "Conversation history retained within a conversation thread.",
        "scope": "conversation",
    },
    "checkpoint": {
        "name": "LangGraph Checkpoint Memory",
        "description": "Conversation state stored through LangGraph checkpointing.",
        "scope": "conversation",
    },
    "long_term": {
        "name": "Long-term Memory",
        "description": "User-scoped information retained across conversations.",
        "scope": "user",
    },
    "cross_thread": {
        "name": "Cross-thread Memory",
        "description": "Tenant-scoped information shared across conversation threads.",
        "scope": "tenant",
    },
    "semantic": {
        "name": "Semantic Memory",
        "description": "Historical information retrieved using semantic similarity.",
        "scope": "user",
    },
    "episodic": {
        "name": "Episodic Memory",
        "description": "Past situations, actions and outcomes stored as experiences.",
        "scope": "conversation",
    },
    "procedural": {
        "name": "Procedural Memory",
        "description": "Operational rules, procedures and behavioral instructions.",
        "scope": "conversation",
    },
    "persistent_db": {
        "name": "Persistent Database Memory",
        "description": "Durable memory intended for relational database persistence.",
        "scope": "conversation",
    },
}


@router.get("/modes")
async def list_memory_modes() -> dict[str, list[dict[str, str]]]:

    modes = []

    for mode_id in (
        "none",
        "short_term",
        "checkpoint",
        "long_term",
        "cross_thread",
        "semantic",
        "episodic",
        "procedural",
        "persistent_db",
    ):
        if mode_id not in SUPPORTED_MEMORY_MODES:
            continue

        metadata = MEMORY_MODE_METADATA[
            mode_id
        ]

        modes.append(
            {
                "id": mode_id,
                "name": metadata["name"],
                "description": metadata["description"],
                "scope": metadata["scope"],
            }
        )

    return {
        "modes": modes
    }