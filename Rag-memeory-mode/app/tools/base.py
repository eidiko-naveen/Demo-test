from typing import Protocol

from app.research.base import ResearchSource


class Tool(Protocol):
    name: str

    async def run(self, query: str, *, limit: int = 5) -> list[ResearchSource]: ...
