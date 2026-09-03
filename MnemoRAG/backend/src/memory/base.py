"""
Abstract interface every memory mode implements. The API layer and Streamlit
frontend only ever talk to this interface — they don't know or care whether
the concrete strategy is Buffer, Summary, Entity, Vector, Persistent, or
Hybrid. Swapping modes is a factory lookup (see factory.py), not a rewrite.
"""
from abc import ABC, abstractmethod


class MemoryStrategy(ABC):
    """
    Contract:
      - add_turn: persist one turn of conversation (called after every
        user message AND every assistant reply).
      - get_context: return a string block of "memory" to prepend to the
        RAG prompt before calling Claude — this is what gives the chatbot
        history retention, distinct from the RAG document context.
    """

    @abstractmethod
    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Persist a single conversation turn for this session."""
        ...

    @abstractmethod
    async def get_context(self, session_id: str, query: str) -> str:
        """
        Build the memory context string for the current query.
        `query` is the user's latest message — strategies that do
        similarity search (Vector, Hybrid, Persistent) use it to find
        relevant past turns; strategies that don't (Buffer, Summary,
        Entity) can ignore it.
        """
        ...

    @property
    def mode_name(self) -> str:
        """Used in API responses / Streamlit UI to show which mode is active."""
        return self.__class__.__name__.replace("Memory", "").lower()