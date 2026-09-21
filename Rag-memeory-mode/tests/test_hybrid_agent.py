import asyncio

from app.agents.hybrid_agent import HybridAgent
from app.research.base import ResearchSource
from app.research.service import ResearchResult


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query: str, *, top_k: int, score_threshold: float | None):
        self.calls += 1
        return [{"score": 0.8, "payload": {"text": "Internal policy", "document_name": "policy.pdf"}}]


class FakeResearch:
    def __init__(self, result: ResearchResult) -> None:
        self.result = result
        self.calls = 0

    async def research(self, query: str, *, limit: int):
        self.calls += 1
        return self.result


class FakeLLM:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return "Combined answer"


def test_external_query_does_not_call_enterprise_retriever() -> None:
    retriever = FakeRetriever()
    research = FakeResearch(ResearchResult([ResearchSource("Report", "https://example.test", "Practice")]))
    agent = HybridAgent(llm=FakeLLM(), retriever=retriever, research_service=research)

    response = asyncio.run(agent.run("What is the latest industry practice?"))

    assert retriever.calls == 0
    assert research.calls == 1
    assert response.used_research is True


def test_comparison_combines_labeled_contexts() -> None:
    retriever = FakeRetriever()
    research = FakeResearch(ResearchResult([ResearchSource("Report", "https://example.test", "Practice")]))
    llm = FakeLLM()
    agent = HybridAgent(llm=llm, retriever=retriever, research_service=research)

    response = asyncio.run(agent.run("Compare our policy with current industry practice"))

    assert retriever.calls == 1
    assert research.calls == 1
    assert response.used_rag is True
    assert response.used_research is True
    assert "<enterprise_context>" in llm.messages[0]["content"]
    assert "<research_context>" in llm.messages[0]["content"]


def test_comparison_keeps_rag_answer_when_research_fails() -> None:
    retriever = FakeRetriever()
    research = FakeResearch(ResearchResult([], error="External research is currently unavailable."))
    agent = HybridAgent(llm=FakeLLM(), retriever=retriever, research_service=research)

    response = asyncio.run(agent.run("Compare our policy with current practice"))

    assert response.used_rag is True
    assert response.used_research is False
    assert response.metadata["external_research_unavailable"] is True
