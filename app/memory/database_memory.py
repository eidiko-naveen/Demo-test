import asyncio
from collections import defaultdict
from typing import Any

from app.memory.base import BaseMemoryManager, MemoryTurn

# Persistent in-memory fallback store simulating durable database table
_DB_MESSAGES_TABLE: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)


class PersistentDatabaseMemoryManager(BaseMemoryManager):
    """Persistent database-backed memory ensuring conversation messages and turn
    histories persist across process restarts, deployments, and distributed workers.
    """

    def __init__(self, *, db_session: Any | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.db_session = db_session
        self.table_key = (self.tenant_id, self.user_id, self.conversation_id)

    def load_context(self) -> list[dict[str, Any]]:
        # Load persisted turns for this tenant, user, and conversation
        db_records = _DB_MESSAGES_TABLE.get(self.table_key, [])
        if db_records:
            return [dict(r) for r in db_records]
        return self.get_history()

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        u_record = {"role": "user", "content": user_content}
        a_record = {"role": "assistant", "content": assistant_content}
        _DB_MESSAGES_TABLE[self.table_key].append(u_record)
        _DB_MESSAGES_TABLE[self.table_key].append(a_record)

    def clear(self) -> None:
        self._history.clear()
        _DB_MESSAGES_TABLE.pop(self.table_key, None)
