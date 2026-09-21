import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI
from langchain_core.chat_history import InMemoryChatMessageHistory
from langgraph.checkpoint.memory import MemorySaver

from app.agents.factory import AgentFactory
from app.api.v1.agents import router as agents_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.memory import router as memory_router
from app.config.settings import Settings, get_settings
from app.database.session import dispose_engine
from app.llm.factory import LLMFactory
from app.memory.factory import MemoryFactory
from app.memory.langchain_memory import LangChainMemoryManager
from app.memory.langgraph_memory import LangGraphMemoryManager
from app.rag.embeddings import EmbeddingFactory
from app.research.base import ResearchSource
from app.research.service import ResearchService
from app.research.web_search import DuckDuckGoSearchProvider
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.tools.web_search import WebSearchTool
from app.utils.logging import configure_logging
from app.vectorstore.qdrant import QdrantVectorStore


def _build_chat_service(
    settings: Settings,
    *,
    checkpointer: MemorySaver | None = None,
) -> ChatService | None:
    if not settings.groq_api_key:
        return None

    try:
        llm = LLMFactory.create(settings)
        embeddings = EmbeddingFactory.create(settings)
        vector_store = QdrantVectorStore(settings)

        # Real async web search tool for live research
        search_provider = DuckDuckGoSearchProvider()
        research_tool = WebSearchTool(search_provider)
        research_service = ResearchService(research_tool)
        resolved_checkpointer = checkpointer if checkpointer is not None else MemorySaver()

        def agent_provider(agent_type: str):
            return AgentFactory.create(
                agent_type,
                settings=settings,
                llm=llm,
                embeddings=embeddings,
                vector_store=vector_store,
                research_service=research_service,
            )

        return ChatService(
            agent_provider,
            checkpointer=resolved_checkpointer,
            embeddings=embeddings,
            window_size=settings.memory_window_size,
        )
    except Exception as exc:
        logging.getLogger("enterprise_rag").exception("Failed to build chat service: %s", exc)
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    logger = logging.getLogger("enterprise_rag")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "Application startup complete: app=%s version=%s environment=%s chat_service=%s",
            resolved_settings.app_name,
            resolved_settings.app_version,
            resolved_settings.app_env,
            "enabled" if application.state.chat_service else "disabled",
        )
        try:
            yield
        finally:
            logger.info("Application shutdown complete: app=%s", resolved_settings.app_name)
            await dispose_engine()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    checkpointer = MemorySaver()

    application.state.settings = resolved_settings
    application.state.checkpointer = checkpointer
    application.state.document_service = DocumentService.from_settings(resolved_settings)
    application.state.chat_service = _build_chat_service(
        resolved_settings,
        checkpointer=checkpointer,
    )

    @application.middleware("http")
    async def add_request_id(request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    application.include_router(
        health_router,
        prefix=resolved_settings.api_v1_prefix,
        dependencies=[Depends(get_settings)],
    )
    for router in (agents_router, chat_router, conversations_router, documents_router, memory_router):
        application.include_router(router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
