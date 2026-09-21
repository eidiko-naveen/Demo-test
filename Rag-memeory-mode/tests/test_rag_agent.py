import asyncio

from app.agents.rag_agent import RAGAgent


class FakeRetriever:
    async def retrieve(self, query: str, *, top_k: int, score_threshold: float | None):
        return [
            {
                "score": 0.9,
                "payload": {
                    "text": "The retention period is seven years.",
                    "document_name": "retention-policy.pdf",
                    "page_number": 4,
                },
            }
        ]


class FakeLLM:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return "The retention period is seven years."


def test_rag_agent_returns_citations_and_labeled_context() -> None:
    llm = FakeLLM()
    agent = RAGAgent(llm=llm, retriever=FakeRetriever())

    response = asyncio.run(
        agent.run("How long is retention?", conversation_context=[{"role": "user", "content": "Hi"}])
    )

    assert response.used_rag is True
    assert response.sources[0].document_name == "retention-policy.pdf"
    assert response.sources[0].page_number == 4
    assert "<enterprise_context>" in llm.messages[0]["content"]
