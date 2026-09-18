from typing import Any

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from app.memory.base import BaseMemoryManager, MemoryTurn


# Global thread store maintaining LangChain chat histories per (tenant, user, conversation)
_SESSION_STORE: dict[tuple[str, str, str], InMemoryChatMessageHistory] = {}


class LangChainMemoryManager(BaseMemoryManager):
    """Production memory manager backed by LangChain chat message history abstractions."""

    def __init__(self, *, window_size: int = 10, **kwargs: Any):
        super().__init__(**kwargs)
        self.window_size = window_size
        self.session_key = (self.tenant_id, self.user_id, self.conversation_id)
        if self.session_key not in _SESSION_STORE:
            _SESSION_STORE[self.session_key] = InMemoryChatMessageHistory()
        self._history_store = _SESSION_STORE[self.session_key]

    def load_context(self) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        for message in self._history_store.messages:
            role = "user" if isinstance(message, HumanMessage) else "assistant"
            context.append({"role": role, "content": str(message.content)})

        # Sliding window pruning for token control
        if self.window_size > 0 and len(context) > self.window_size * 2:
            context = context[-self.window_size * 2 :]
        return context

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        self._history_store.add_user_message(user_content)
        self._history_store.add_ai_message(assistant_content)

    def clear(self) -> None:
        self._history.clear()
        self._history_store.clear()
