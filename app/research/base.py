from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ResearchSource:
    title: str
    url: str
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchProvider(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[ResearchSource]: ...


class ResearchTool(Protocol):
    async def run(self, query: str, *, limit: int = 5) -> list[ResearchSource]: ...
