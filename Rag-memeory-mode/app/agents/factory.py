from typing import Any

from app.agents.hybrid_agent import HybridAgent
from app.agents.rag_agent import RAGAgent
from app.agents.research_agent import ResearchAgent
from app.config.settings import Settings
from app.llm.base import LLMProvider
from app.rag.embeddings import EmbeddingProvider
from app.rag.retriever import EnterpriseRetriever
from app.research.service import ResearchService
from app.vectorstore.base import VectorStore


class AgentFactory:
    @staticmethod
    def create(
        agent_type: str,
        *,
        settings: Settings,
        llm: LLMProvider,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        research_service: ResearchService,
    ) -> Any:
        retriever = EnterpriseRetriever(embeddings, vector_store)
        normalized = agent_type.lower().replace(" ", "_")
        if normalized in {"rag", "rag_agent"}:
            return RAGAgent(llm=llm, retriever=retriever)
        if normalized in {"research", "research_agent"}:
            return ResearchAgent(llm=llm, research_service=research_service)
        if normalized in {"hybrid", "hybrid_agent"}:
            return HybridAgent(
                llm=llm,
                retriever=retriever,
                research_service=research_service,
            )
        raise ValueError(f"Unsupported agent type: {agent_type}")
