from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryTurn:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            **self.metadata,
        }


class BaseMemoryManager(ABC):
    """
    Common interface for all memory implementations.

    Memory managers are intentionally provider-independent. Each implementation
    can use in-memory state, LangGraph checkpoints, embeddings, or a database.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self._history: list[MemoryTurn] = []

    @abstractmethod
    def load_context(
        self,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Load memory context relevant to the current query.

        Implementations that do not need the query can ignore it.
        """

    @abstractmethod
    def save_turn(
        self,
        user_content: str,
        assistant_content: str,
    ) -> None:
        """Persist the current conversation turn."""

    @abstractmethod
    def clear(self) -> None:
        """Clear memory for the current scope."""

    def get_history(self) -> list[dict[str, Any]]:
        return [
            turn.as_message()
            for turn in self._history
        ]

    def summarize(self) -> str:
        return "\n".join(
            f"{turn.role}: {turn.content}"
            for turn in self._history
        )

    def get_relevant_memories(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        """
        Lightweight lexical fallback used by memory implementations
        when semantic retrieval is unavailable.
        """

        query_terms = {
            term
            for term in query.lower().split()
            if term.strip()
        }

        results = []

        for turn in self._history:
            content_terms = set(
                turn.content.lower().split()
            )

            if query_terms.intersection(content_terms):
                results.append(turn.as_message())

        return results

    def _save_messages(
        self,
        user_content: str,
        assistant_content: str,
    ) -> None:
        self._history.extend(
            [
                MemoryTurn(
                    role="user",
                    content=user_content,
                ),
                MemoryTurn(
                    role="assistant",
                    content=assistant_content,
                ),
            ]
        )