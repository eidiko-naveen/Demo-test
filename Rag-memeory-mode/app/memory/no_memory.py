from typing import Any

from app.memory.base import BaseMemoryManager


class NoMemoryManager(BaseMemoryManager):
    def load_context(self) -> list[dict[str, Any]]:
        return []

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        return None

    def clear(self) -> None:
        return None

    def get_history(self) -> list[dict[str, Any]]:
        return []
