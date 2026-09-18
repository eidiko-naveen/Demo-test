import logging
from typing import Any

from app.graph.state import AgentState
from app.memory.factory import MemoryFactory


logger = logging.getLogger("enterprise_rag")


def _get_dependencies(
    state: AgentState,
) -> dict[str, Any]:

    return {
        "checkpointer": state.get(
            "checkpointer"
        ),
        "embeddings": state.get(
            "embeddings"
        ),
        "window_size": state.get(
            "memory_window_size",
            10,
        ),
    }


async def load_memory(
    state: AgentState,
) -> AgentState:

    mode = MemoryFactory.normalize_mode(
        state.get("memory_mode")
        or "none"
    )

    if mode == "none":
        return {
            **state,
            "conversation_context": [],
        }

    try:
        manager = MemoryFactory.create(
            mode,
            tenant_id=state.get(
                "tenant_id"
            )
            or "development-tenant",
            user_id=state.get(
                "user_id"
            )
            or "development-user",
            conversation_id=state.get(
                "conversation_id"
            )
            or "default",
            **_get_dependencies(state),
        )

        context = manager.load_context(
            query=state.get("query")
        )

        return {
            **state,
            "conversation_context": context,
        }

    except Exception as exc:
        logger.warning(
            "Graph memory load failed: mode=%s error=%s",
            mode,
            exc,
        )

        return {
            **state,
            "conversation_context": [],
            "errors": [
                *state.get("errors", []),
                f"Memory load failed: {mode}",
            ],
        }


async def save_memory(
    state: AgentState,
) -> AgentState:

    mode = MemoryFactory.normalize_mode(
        state.get("memory_mode")
        or "none"
    )

    if mode == "none":
        return state

    query = state.get("query")
    answer = state.get("final_answer")

    if not query or not answer:
        return state

    try:
        manager = MemoryFactory.create(
            mode,
            tenant_id=state.get(
                "tenant_id"
            )
            or "development-tenant",
            user_id=state.get(
                "user_id"
            )
            or "development-user",
            conversation_id=state.get(
                "conversation_id"
            )
            or "default",
            **_get_dependencies(state),
        )

        manager.save_turn(
            query,
            answer,
        )

    except Exception as exc:
        logger.warning(
            "Graph memory save failed: mode=%s error=%s",
            mode,
            exc,
        )

    return state