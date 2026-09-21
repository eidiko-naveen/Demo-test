from typing import Any

from app.llm.base import LLMProvider
from app.prompts.research import build_research_messages
from app.research.service import ResearchService
from app.schemas.response import AgentResponse, SourceReference
from app.services.context_assembler import ContextAssembler


class ResearchAgent:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        research_service: ResearchService,
        context_assembler: ContextAssembler | None = None,
    ):
        self.llm = llm
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
        limit: int = 5,
        **kwargs: Any,
    ) -> AgentResponse:

        result = await self.research_service.research(
            query,
            limit=limit,
        )

        if result.error:
            return AgentResponse(
                answer=result.error,
                agent_type="research",
                memory_mode=memory_mode,
                used_research=False,
                conversation_id=conversation_id,
                metadata={
                    "research_error": True,
                },
            )

        research_context = "\n\n".join(
            f"[{index}] {source.title}\n"
            f"URL: {source.url}\n"
            f"{source.snippet}"
            for index, source in enumerate(
                result.sources,
                start=1,
            )
        )

        conversation_context_text = (
            self.context_assembler.assemble_conversation(
                conversation_context or []
            )
        )

        if not result.sources:
            answer = (
                "I could not find external research "
                "results for this question."
            )
        else:
            answer = await self.llm.ainvoke(
                build_research_messages(
                    query=query,
                    research_context=research_context,
                    conversation_context=conversation_context_text,
                )
            )

        return AgentResponse(
            answer=answer,
            agent_type="research",
            memory_mode=memory_mode,
            sources=[
                SourceReference(
                    document_name=source.title,
                    source=source.url,
                )
                for source in result.sources
            ],
            used_research=bool(
                result.sources
            ),
            conversation_id=conversation_id,
            metadata={
                "research_source_count": len(
                    result.sources
                ),
            },
        )