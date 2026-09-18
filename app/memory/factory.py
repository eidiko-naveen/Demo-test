from typing import Any

from app.memory.base import BaseMemoryManager
from app.memory.cross_thread_memory import CrossThreadMemoryManager
from app.memory.database_memory import PersistentDatabaseMemoryManager
from app.memory.episodic_memory import EpisodicMemoryManager
from app.memory.langchain_memory import LangChainMemoryManager
from app.memory.langgraph_memory import LangGraphMemoryManager
from app.memory.long_term_memory import LongTermMemoryManager
from app.memory.no_memory import NoMemoryManager
from app.memory.procedural_memory import ProceduralMemoryManager
from app.memory.semantic_memory import SemanticMemoryManager


SUPPORTED_MEMORY_MODES = {
    "none",
    "short_term",
    "checkpoint",
    "long_term",
    "cross_thread",
    "semantic",
    "episodic",
    "procedural",
    "persistent_db",
}


class MemoryFactory:
    """
    Central factory for all supported memory implementations.

    Supported modes:

    - none
    - short_term
    - checkpoint
    - long_term
    - cross_thread
    - semantic
    - episodic
    - procedural
    - persistent_db
    """

    @staticmethod
    def normalize_mode(mode: str | None) -> str:
        normalized = (
            mode or "none"
        ).lower().strip().replace(" ", "_").replace("-", "_").replace("/", "_")

        aliases = {
            "stateless": "none",
            "no_memory": "none",
            "short_term_memory": "short_term",
            "thread_memory": "short_term",
            "checkpoint_memory": "checkpoint",
            "long_term_memory": "long_term",
            "cross_thread_memory": "cross_thread",
            "semantic_memory": "semantic",
            "episodic_memory": "episodic",
            "procedural_memory": "procedural",
            "persistent": "persistent_db",
            "database": "persistent_db",
            "persistent_database": "persistent_db",
        }

        return aliases.get(normalized, normalized)

    @classmethod
    def is_supported(cls, mode: str | None) -> bool:
        return cls.normalize_mode(mode) in SUPPORTED_MEMORY_MODES

    @classmethod
    def create(
        cls,
        mode: str,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        window_size: int = 10,
        checkpointer: Any | None = None,
        embeddings: Any | None = None,
        db_session: Any | None = None,
        **kwargs: Any,
    ) -> BaseMemoryManager:

        normalized = cls.normalize_mode(mode)

        common = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
        }

        if normalized == "none":
            return NoMemoryManager(**common)

        if normalized == "short_term":
            return LangChainMemoryManager(
                window_size=window_size,
                **common,
            )

        if normalized == "checkpoint":
            return LangGraphMemoryManager(
                checkpointer=checkpointer,
                window_size=window_size,
                **common,
            )

        if normalized == "long_term":
            return LongTermMemoryManager(**common)

        if normalized == "cross_thread":
            return CrossThreadMemoryManager(**common)

        if normalized == "semantic":
            return SemanticMemoryManager(
                embeddings=embeddings,
                **common,
            )

        if normalized == "episodic":
            return EpisodicMemoryManager(**common)

        if normalized == "procedural":
            return ProceduralMemoryManager(**common)

        if normalized == "persistent_db":
            return PersistentDatabaseMemoryManager(
                db_session=db_session,
                **common,
            )

        raise ValueError(
            f"Unsupported memory mode '{mode}'. "
            f"Supported modes: {sorted(SUPPORTED_MEMORY_MODES)}"
        )