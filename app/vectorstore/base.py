from typing import Any, Protocol


class VectorStore(Protocol):
    async def ensure_collection(self) -> None: ...

    async def upsert(
        self, point_ids: list[str], vectors: list[list[float]], payloads: list[dict[str, Any]]
    ) -> None: ...

    async def similarity_search(
        self, vector: list[float], *, top_k: int, score_threshold: float | None = None
    ) -> list[dict[str, Any]]: ...

    async def health_check(self) -> bool: ...
