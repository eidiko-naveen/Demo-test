from typing import Any, Literal

from app.llm.base import LLMProvider
from app.prompts.hybrid import build_hybrid_messages
from app.rag.retriever import EnterpriseRetriever
from app.research.service import ResearchService
from app.schemas.response import AgentResponse, SourceReference
from app.services.context_assembler import ContextAssembler


HybridRoute = Literal[
    "enterprise",
    "external",
    "both",
]


def classify_hybrid_query(
    query: str,
) -> HybridRoute:

    normalized = query.lower()

    comparison_terms = (
        "compare",
        "comparison",
        "versus",
        " vs ",
        "according to",
        "against",
    )

    external_terms = (
        "latest",
        "current",
        "today",
        "recent",
        "industry",
        "research",
        "news",
    )

    if any(
        term in normalized
        for term in comparison_terms
    ):
        return "both"

    if any(
        term in normalized
        for term in external_terms
    ):
        return "external"

    return "enterprise"


class HybridAgent:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        retriever: EnterpriseRetriever,
        research_service: ResearchService,
        context_assembler: ContextAssembler | None = None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.research_service = research_service
        self.context_assembler = (
            context_assembler
            or ContextAssembler()
        )

    async def run(
        self,
        query: str,
        *,
        conversation_context: list[dict[str, Any]] | None = None,
        memory_mode: str = "none",
        conversation_id: str | None = None,
        top_k: int = 5,
        score_threshold: float | None = None,
        research_limit: int = 5,
        **kwargs: Any,
    ) -> AgentResponse:

        route = classify_hybrid_query(
            query
        )

        documents: list[
            dict[str, Any]
        ] = []

        research_result = None

        if route in {
            "enterprise",
            "both",
        }:
            documents = await self.retriever.retrieve(
                query,
                top_k=top_k,
                score_threshold=score_threshold,
            )

        if route in {
            "external",
            "both",
        }:
            research_result = (
                await self.research_service.research(
                    query,
                    limit=research_limit,
                )
            )

        conversation_text = (
            self.context_assembler.assemble_conversation(
                conversation_context or []
            )
        )

        if route == "enterprise":
            return await self._enterprise_response(
                query=query,
                documents=documents,
                memory_mode=memory_mode,
                conversation_id=conversation_id,
                conversation_context=conversation_text,
            )

        if route == "external":
            return await self._external_response(
                query=query,
                result=research_result,
                memory_mode=memory_mode,
                conversation_id=conversation_id,
                conversation_context=conversation_text,
            )

        return await self._combined_response(
            query=query,
            documents=documents,
            result=research_result,
            memory_mode=memory_mode,
            conversation_id=conversation_id,
            conversation_context=conversation_text,
        )

    async def _enterprise_response(
        self,
        *,
        query: str,
        documents: list[dict[str, Any]],
        memory_mode: str,
        conversation_id: str | None,
        conversation_context: str,
    ) -> AgentResponse:

        if not documents:
            if conversation_context:
                answer = await self.llm.ainvoke(
                    build_hybrid_messages(
                        query=query,
                        enterprise_context="",
                        research_context="",
                        conversation_context=conversation_context,
                    )
                )

                return AgentResponse(
                    answer=answer,
                    agent_type="hybrid",
                    memory_mode=memory_mode,
                    conversation_id=conversation_id,
                    metadata={
                        "enterprise_documents_found": 0,
                    },
                )

            return AgentResponse(
                answer=(
                    "I could not find relevant information "
                    "in the enterprise knowledge base."
                ),
                agent_type="hybrid",
                memory_mode=memory_mode,
                used_rag=True,
                confidence=0.0,
                conversation_id=conversation_id,
            )

        enterprise_context = (
            self.context_assembler.assemble_enterprise(
                documents
            )
        )

        answer = await self.llm.ainvoke(
            build_hybrid_messages(
                query=query,
                enterprise_context=enterprise_context,
                research_context="",
                conversation_context=conversation_context,
            )
        )

        return AgentResponse(
            answer=answer,
            agent_type="hybrid",
            memory_mode=memory_mode,
            sources=self._enterprise_sources(
                documents
            ),
            used_rag=True,
            conversation_id=conversation_id,
        )

    async def _external_response(
        self,
        *,
        query: str,
        result: Any,
        memory_mode: str,
        conversation_id: str | None,
        conversation_context: str,
    ) -> AgentResponse:

        if (
            result is None
            or result.error
            or not result.sources
        ):
            return AgentResponse(
                answer=(
                    result.error
                    if result and result.error
                    else "External research returned no results."
                ),
                agent_type="hybrid",
                memory_mode=memory_mode,
                conversation_id=conversation_id,
            )

        research_context = "\n\n".join(
            f"{source.title}\n"
            f"URL: {source.url}\n"
            f"{source.snippet}"
            for source in result.sources
        )

        answer = await self.llm.ainvoke(
            build_hybrid_messages(
                query=query,
                enterprise_context="",
                research_context=research_context,
                conversation_context=conversation_context,
            )
        )

        return AgentResponse(
            answer=answer,
            agent_type="hybrid",
            memory_mode=memory_mode,
            sources=[
                SourceReference(
                    document_name=source.title,
                    source=source.url,
                )
                for source in result.sources
            ],
            used_research=True,
            conversation_id=conversation_id,
        )

    async def _combined_response(
        self,
        *,
        query: str,
        documents: list[dict[str, Any]],
        result: Any,
        memory_mode: str,
        conversation_id: str | None,
        conversation_context: str,
    ) -> AgentResponse:

        research_sources = (
            result.sources
            if result
            and not result.error
            else []
        )

        if (
            not documents
            and not research_sources
        ):
            return AgentResponse(
                answer=(
                    "I could not find sufficient "
                    "enterprise or external information "
                    "for this question."
                ),
                agent_type="hybrid",
                memory_mode=memory_mode,
                conversation_id=conversation_id,
            )

        enterprise_context = (
            self.context_assembler.assemble_enterprise(
                documents
            )
        )

        research_context = "\n\n".join(
            f"{source.title}\n"
            f"URL: {source.url}\n"
            f"{source.snippet}"
            for source in research_sources
        )

        answer = await self.llm.ainvoke(
            build_hybrid_messages(
                query=query,
                enterprise_context=enterprise_context,
                research_context=research_context,
                conversation_context=conversation_context,
            )
        )

        return AgentResponse(
            answer=answer,
            agent_type="hybrid",
            memory_mode=memory_mode,
            sources=(
                self._enterprise_sources(
                    documents
                )
                + [
                    SourceReference(
                        document_name=source.title,
                        source=source.url,
                    )
                    for source in research_sources
                ]
            ),
            used_rag=bool(documents),
            used_research=bool(
                research_sources
            ),
            conversation_id=conversation_id,
            metadata={
                "external_research_unavailable": bool(
                    result and result.error
                )
            },
        )

    @staticmethod
    def _enterprise_sources(
        documents: list[dict[str, Any]],
    ) -> list[SourceReference]:

        return [
            SourceReference(
                document_name=str(
                    document.get(
                        "payload",
                        {},
                    ).get(
                        "document_name",
                        "Unknown document",
                    )
                ),
                page_number=document.get(
                    "payload",
                    {},
                ).get("page_number"),
                source=document.get(
                    "payload",
                    {},
                ).get("source"),
                score=document.get(
                    "score"
                ),
            )
            for document in documents
        ]