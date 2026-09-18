from collections import defaultdict
from typing import Any

from app.memory.base import BaseMemoryManager, MemoryTurn

# Global storage scoped by tenant_id shared across threads
_TENANT_STORE: dict[str, list[dict[str, Any]]] = defaultdict(list)


class CrossThreadMemoryManager(BaseMemoryManager):
    """Cross-thread memory enabling knowledge, facts, and insights discovered
    in one conversation thread to be shared and referenced across threads in the workspace.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    def load_context(self) -> list[dict[str, Any]]:
        shared_turns = _TENANT_STORE.get(self.tenant_id, [])
        context: list[dict[str, Any]] = []
        if shared_turns:
            # Inject relevant cross-thread insights
            cross_thread_notes = [
                f"[Thread {t.get('conversation_id', 'unknown')}]: {t.get('content')}"
                for t in shared_turns[-8:]
                if t.get("conversation_id") != self.conversation_id
            ]
            if cross_thread_notes:
                context.append(
                    {
                        "role": "system",
                        "content": "Cross-thread workspace context:\n" + "\n".join(cross_thread_notes),
                    }
                )
        return context + self.get_history()

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        _TENANT_STORE[self.tenant_id].append(
            {
                "user_id": self.user_id,
                "conversation_id": self.conversation_id,
                "content": f"User: {user_content} | Assistant: {assistant_content[:150]}",
            }
        )

    def clear(self) -> None:
        self._history.clear()
        _TENANT_STORE.pop(self.tenant_id, None)
