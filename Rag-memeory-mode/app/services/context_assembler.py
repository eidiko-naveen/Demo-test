from typing import Any


class ContextAssembler:
    """Keep memory, enterprise documents, and research visibly separated."""

    def assemble_conversation(self, messages: list[dict[str, Any]]) -> str:
        return "\n".join(f"{message.get('role', 'unknown')}: {message.get('content', '')}" for message in messages)

    def assemble_enterprise(self, documents: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            f"[{index}] {document.get('payload', {}).get('text', '')}"
            for index, document in enumerate(documents, start=1)
        )
