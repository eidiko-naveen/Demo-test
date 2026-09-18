from datetime import datetime, timezone
from typing import Any

from app.memory.base import BaseMemoryManager, MemoryTurn


class EpisodicMemoryManager(BaseMemoryManager):
    """Episodic memory capturing structured historical interaction episodes:
    time, situational query, actions taken, and final outcome.
    Allows agents to recall specific past scenarios and lessons learned.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._episodes: list[dict[str, Any]] = []

    def load_context(self) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        if self._episodes:
            formatted_episodes = []
            for ep in self._episodes[-5:]:
                formatted_episodes.append(
                    f"• Episode [{ep['timestamp']}]: Situation: '{ep['situation']}' -> Outcome: '{ep['outcome'][:120]}...'"
                )
            context.append(
                {
                    "role": "system",
                    "content": "Past episodic experience recall:\n" + "\n".join(formatted_episodes),
                }
            )
        return context + self.get_history()

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        self.save_episode(situation=user_content, outcome=assistant_content)

    def save_episode(
        self,
        situation: str,
        action: str = "",
        outcome: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        episode = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "situation": situation,
            "action": action,
            "outcome": outcome,
            "metadata": metadata or {},
            "conversation_id": self.conversation_id,
        }
        self._episodes.append(episode)

    def get_episodes(self) -> list[dict[str, Any]]:
        return list(self._episodes)

    def clear(self) -> None:
        self._history.clear()
        self._episodes.clear()
