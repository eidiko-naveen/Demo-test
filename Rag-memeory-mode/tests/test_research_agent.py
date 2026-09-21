import asyncio

from app.agents.research_agent import ResearchAgent
from app.research.base import ResearchSource
from app.research.service import ResearchService
from app.tools.web_search import WebSearchTool


class FakeProvider:
    async def search(self, query: str, *, limit: int):
        return [ResearchSource("Industry report", "https://example.test/report", "Current practice")]


class FailingProvider:
    async def search(self, query: str, *, limit: int):
        raise RuntimeError("provider unavailable")


class FakeLLM:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return "Research-backed answer."


def test_research_agent_returns_external_citation() -> None:
    llm = FakeLLM()
    service = ResearchService(WebSearchTool(FakeProvider()))
    agent = ResearchAgent(llm=llm, research_service=service)

    response = asyncio.run(agent.run("What is current practice?"))

    assert response.used_research is True
    assert response.sources[0].source == "https://example.test/report"
    assert "<research_context>" in llm.messages[0]["content"]


def test_research_agent_degrades_when_provider_fails() -> None:
    service = ResearchService(WebSearchTool(FailingProvider()))
    agent = ResearchAgent(llm=FakeLLM(), research_service=service)

    response = asyncio.run(agent.run("Find current practice"))

    assert response.used_research is False
    assert response.metadata["research_error"] is True
    assert "unavailable" in response.answer
