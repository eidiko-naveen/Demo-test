from typing import Any

from app.memory.base import BaseMemoryManager, MemoryTurn

DEFAULT_PROCEDURES = [
    "Procedure 1: Verify all claims against enterprise documentation before providing conclusive statements.",
    "Procedure 2: In research mode, distinguish between verified enterprise facts and external internet sources.",
    "Procedure 3: Structure output with concise summaries, clear bullet points, and accurate source citations.",
    "Procedure 4: Flag ambiguous or conflicting information explicitly to the user.",
]


class ProceduralMemoryManager(BaseMemoryManager):
    """Procedural memory providing the agent with operational protocols,
    standard operating procedures (SOPs), tool guidelines, and workflow rules.
    """

    def __init__(self, *, procedures: list[str] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.procedures = list(procedures) if procedures is not None else list(DEFAULT_PROCEDURES)

    def load_context(self) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        if self.procedures:
            formatted_rules = "\n".join(f"- {p}" for p in self.procedures)
            context.append(
                {
                    "role": "system",
                    "content": f"Operational Guidelines & Procedural Rules:\n{formatted_rules}",
                }
            )
        return context + self.get_history()

    def add_procedure(self, name_or_procedure: str, details: str | None = None) -> None:
        procedure = f"{name_or_procedure}: {details}" if details else name_or_procedure
        if procedure not in self.procedures:
            self.procedures.append(procedure)

    def save_turn(self, user_content: str, assistant_content: str) -> None:
        self._save_messages(user_content, assistant_content)
        # Learn operational directives dynamically if mentioned by user
        lowered = user_content.lower()
        if "always " in lowered or "never " in lowered or "rule:" in lowered:
            self.add_procedure(f"User Directive: {user_content}")

    def clear(self) -> None:
        self._history.clear()
        self.procedures = list(DEFAULT_PROCEDURES)
