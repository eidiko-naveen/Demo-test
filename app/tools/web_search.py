from app.research.base import ResearchSource, SearchProvider


class WebSearchTool:
    name = "web_search"

    def __init__(self, provider: SearchProvider):
        self.provider = provider

    async def run(self, query: str, *, limit: int = 5) -> list[ResearchSource]:
        return await self.provider.search(query, limit=limit)
