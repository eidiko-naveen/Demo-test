import math
from collections import defaultdict
from typing import Any

from app.memory.base import BaseMemoryManager


def _cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    if not vector_a or not vector_b:
        return 0.0

    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(
        a * b
        for a, b in zip(vector_a, vector_b)
    )

    norm_a = math.sqrt(
        sum(a * a for a in vector_a)
    )

    norm_b = math.sqrt(
        sum(b * b for b in vector_b)
    )

    if not norm_a or not norm_b:
        return 0.0

    return dot_product / (norm_a * norm_b)


# Application-process semantic memory store.
#
# Key:
#     (tenant_id, user_id)
#
# The store is intentionally scoped by tenant and user.
# For multi-worker production deployments, this should eventually move
# to a persistent vector memory store.
_SEMANTIC_STORE: dict[
    tuple[str, str],
    list[tuple[dict[str, Any], list[float] | None]],
] = defaultdict(list)


class SemanticMemoryManager(BaseMemoryManager):
    """
    Semantic memory based on embeddings and cosine similarity.

    Memory is scoped to a tenant + user so information is not accidentally
    shared across tenants.
    """

    def __init__(
        self,
        *,
        embeddings: Any | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)

        self.embeddings = embeddings
        self.store_key = (
            self.tenant_id,
            self.user_id,
        )

    @property
    def _store(self):
        return _SEMANTIC_STORE[self.store_key]

    def load_context(
        self,
        query: str | None = None,
    ) -> list[dict[str, Any]]:

        if not query:
            return self.get_history()

        relevant = self.get_relevant_memories(
            query,
            top_k=6,
        )

        if not relevant:
            return self.get_history()

        semantic_context = {
            "role": "system",
            "content": (
                "Relevant semantic memory:\n"
                + "\n".join(
                    f"- {item.get('role', 'memory')}: "
                    f"{item.get('content', '')}"
                    for item in relevant
                )
            ),
        }

        return [
            semantic_context,
            *relevant,
        ]

    def get_relevant_memories(
        self,
        query: str,
        *,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:

        if not self._store:
            return []

        if self.embeddings is not None:
            try:
                query_vector = self.embeddings.embed_query(
                    query
                )

                scored = []

                for memory, vector in self._store:
                    score = _cosine_similarity(
                        query_vector,
                        vector or [],
                    )

                    scored.append(
                        (
                            score,
                            memory,
                        )
                    )

                scored.sort(
                    key=lambda item: item[0],
                    reverse=True,
                )

                return [
                    memory
                    for score, memory in scored[:top_k]
                    if score >= 0.20
                ]

            except Exception:
                # Fall back to lexical retrieval.
                pass

        query_terms = {
            term
            for term in query.lower().split()
            if term.strip()
        }

        scored = []

        for memory, _ in self._store:
            content = str(
                memory.get("content", "")
            ).lower()

            content_terms = set(
                content.split()
            )

            overlap = len(
                query_terms.intersection(
                    content_terms
                )
            )

            scored.append(
                (
                    overlap,
                    memory,
                )
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            memory
            for score, memory in scored[:top_k]
            if score > 0
        ]

    def save_turn(
        self,
        user_content: str,
        assistant_content: str,
    ) -> None:

        self._save_messages(
            user_content,
            assistant_content,
        )

        messages = [
            {
                "role": "user",
                "content": user_content,
                "conversation_id": self.conversation_id,
            },
            {
                "role": "assistant",
                "content": assistant_content,
                "conversation_id": self.conversation_id,
            },
        ]

        vectors: list[list[float] | None] = [
            None,
            None,
        ]

        if self.embeddings is not None:
            try:
                embedded = self.embeddings.embed_documents(
                    [
                        user_content,
                        assistant_content,
                    ]
                )

                if isinstance(embedded, list):
                    for index in range(
                        min(len(embedded), 2)
                    ):
                        if isinstance(
                            embedded[index],
                            list,
                        ):
                            vectors[index] = embedded[index]

            except Exception:
                pass

        for message, vector in zip(
            messages,
            vectors,
        ):
            self._store.append(
                (
                    message,
                    vector,
                )
            )

    def clear(self) -> None:
        self._history.clear()
        _SEMANTIC_STORE.pop(
            self.store_key,
            None,
        )