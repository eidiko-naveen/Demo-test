from dataclasses import dataclass

from app.research.base import ResearchSource, ResearchTool


@dataclass(slots=True)
class ResearchResult:
    sources: list[ResearchSource]
    error: str | None = None


class ResearchService:
    def __init__(self, tool: ResearchTool):
        self.tool = tool

    async def research(self, query: str, *, limit: int = 5) -> ResearchResult:
        try:
            sources = await self.tool.run(query, limit=limit)
            return ResearchResult(sources=sources)
        except Exception:
            return ResearchResult(sources=[], error="External research is currently unavailable.")
