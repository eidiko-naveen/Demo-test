from typing import Any

import langgraph.checkpoint.base as checkpoint_base
from langgraph.checkpoint.memory import MemorySaver

from app.memory.base import BaseMemoryManager, MemoryTurn


class LangGraphMemoryManager(BaseMemoryManager):
    """Production memory manager backed by LangGraph MemorySaver checkpointing."""

    def __init__(
        self,
        *,
        checkpointer: MemorySaver | None = None,
        window_size: int = 10,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.checkpointer = checkpointer if checkpointer is not None else MemorySaver()
        self.window_size = window_size

    @property
    def config(self) -> dict[str, dict[str, str]]:
        thread_id = f"{self.tenant_id}:{self.user_id}:{self.conversation_id}"
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    def load_context(self) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        try:
            tuple_record = self.checkpointer.get_tuple(self.config)
            if tuple_record and tuple_record.checkpoint:
                channel_values = tuple_record.checkpoint.get("channel_values", {})
                messages = channel_values.get("messages")
                if isinstance(messages, list):
                    context = [dict(m) for m in messages]
        except Exception:
            context = []

        if not context:
            context = self.get_history()

        if self.window_size > 0 and len(context) > self.window_size * 2:
            context = context[-self.window_size * 2 :]
        return context

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        try:
            checkpoint = checkpoint_base.empty_checkpoint()
            current_history = self.get_history()
            checkpoint["channel_values"] = {
                "messages": current_history,
                "last_user": user_content,
                "last_assistant": assistant_content,
            }
            checkpoint["channel_versions"] = {"messages": len(current_history)}
            self.checkpointer.put(self.config, checkpoint, {}, {"messages": len(current_history)})
        except Exception:
            pass

    def clear(self) -> None:
        self._history.clear()
        try:
            checkpoint = checkpoint_base.empty_checkpoint()
            checkpoint["channel_values"] = {"messages": []}
            self.checkpointer.put(self.config, checkpoint, {}, {"messages": 0})
        except Exception:
            pass
