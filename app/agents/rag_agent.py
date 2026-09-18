from typing import Any

from app.agents.base import Agent
from app.llm.base import LLMProvider
from app.prompts.rag import build_rag_messages
from app.schemas.response import AgentResponse, SourceReference
from app.services.context_assembler import ContextAssembler
from app.vectorstore.base import VectorStore
from app.rag.embeddings import EmbeddingProvider
from app.rag.retriever import EnterpriseRetriever


class RAGAgent:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        retriever: EnterpriseRetriever,
        context_assembler: ContextAssembler | None = None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.context_assembler = context_assembler or ContextAssembler()

    @classmethod
    def from_components(
        cls, *, llm: LLMProvider, embeddings: EmbeddingProvider, vector_store: VectorStore
    ) -> "RAGAgent":
        return cls(llm=llm, retriever=EnterpriseRetriever(embeddings, vector_store))

    async def run(
        self,
        query: str,
        *,
        conversation_context: list[dict[str, Any]] | None = None,
        memory_mode: str = "none",
        conversation_id: str | None = None,
        top_k: int = 5,
        score_threshold: float | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        documents = await self.retriever.retrieve(
            query, top_k=top_k, score_threshold=score_threshold
        )
        sources = self._sources_from_documents(documents)
        if not documents:
            return AgentResponse(
                answer="I could not find relevant information in the enterprise knowledge base.",
                agent_type="rag",
                memory_mode=memory_mode,
                sources=[],
                confidence=0.0,
                used_rag=True,
                conversation_id=conversation_id,
            )
        messages = build_rag_messages(
            query,
            self.context_assembler.assemble_conversation(conversation_context or []),
            self.context_assembler.assemble_enterprise(documents),
        )
        answer = await self.llm.ainvoke(messages)
        scores = [source.score for source in sources if source.score is not None]
        return AgentResponse(
            answer=answer,
            agent_type="rag",
            memory_mode=memory_mode,
            sources=sources,
            confidence=sum(scores) / len(scores) if scores else None,
            used_rag=True,
            conversation_id=conversation_id,
        )

    @staticmethod
    def _sources_from_documents(documents: list[dict[str, Any]]) -> list[SourceReference]:
        sources: list[SourceReference] = []
        for document in documents:
            payload = document.get("payload", {})
            sources.append(
                SourceReference(
                    document_name=str(payload.get("document_name", "Unknown document")),
                    page_number=payload.get("page_number"),
                    source=payload.get("source"),
                    score=document.get("score"),
                )
            )
        return sources
