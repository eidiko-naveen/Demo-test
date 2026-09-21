import re
from collections import defaultdict
from typing import Any

from app.memory.base import BaseMemoryManager, MemoryTurn

# Global storage scoped by (tenant_id, user_id) simulating LangGraph user store
_USER_STORE: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
_USER_PROFILE_STORE: dict[tuple[str, str], dict[str, str]] = {}


def _extract_user_name(text: str) -> str | None:
    patterns = (
        r"\bmy name is\s+(.+)",
        r"\bi am\s+(.+)",
        r"\bcall me\s+(.+)",
        r"\bi'm\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        candidate = match.group(1).strip().strip(".?!,;:")
        if not candidate:
            continue

        stop_words = {
            "and", "but", "because", "while", "since", "if", "when", "where",
            "who", "what", "how", "i", "we", "you", "they", "he", "she", "it",
            "work", "live", "am", "from", "in", "at", "on", "with", "for", "to",
            "is", "are", "was", "were", "have", "has", "do", "does", "did",
            "can", "could", "will", "would", "should", "my", "our", "your",
            "their", "his", "her", "its"
        }
        for delimiter in [" and ", " but ", " because ", " while ", " since ", " if ", " when ", " where ", " who ", " what ", " how ", " i ", " we ", " you ", " they ", " he ", " she ", " it ", " work ", " live ", " am ", " from ", " in ", " at ", " on ", " with ", " for ", " to "]:
            if delimiter in candidate.lower():
                candidate = candidate.split(delimiter)[0].strip()
                break

        candidate = re.sub(r"[\s]+", " ", candidate).strip(".?!,;:")
        if candidate and len(candidate.split()) <= 3:
            return candidate
    return None


class LongTermMemoryManager(BaseMemoryManager):
    """Long-term memory scoped to the user across all conversation threads.
    Preserves user profile facts, preferences, and multi-session knowledge.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.store_key = (self.tenant_id, self.user_id)

    def get_user_profile(self) -> dict[str, str]:
        return dict(_USER_PROFILE_STORE.get(self.store_key, {}))

    def load_context(self) -> list[dict[str, Any]]:
        user_memories = _USER_STORE.get(self.store_key, [])
        context: list[dict[str, Any]] = []
        profile = self.get_user_profile()
        if profile:
            profile_summary = "; ".join(f"{key}: {value}" for key, value in profile.items())
            context.append({"role": "system", "content": f"User profile: {profile_summary}"})
        if user_memories:
            summary_facts = "\n".join(
                f"- User fact: {m.get('content')}" for m in user_memories[-10:]
            )
            context.append({"role": "system", "content": f"Long-term user profile:\n{summary_facts}"})
        return context + self.get_history()

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        name = _extract_user_name(user_content)
        if name:
            _USER_PROFILE_STORE[self.store_key] = {"name": name}
        _USER_STORE[self.store_key].append(
            {"role": "user", "content": user_content, "conversation_id": self.conversation_id}
        )

    def clear(self) -> None:
        self._history.clear()
        _USER_STORE.pop(self.store_key, None)
        _USER_PROFILE_STORE.pop(self.store_key, None)
