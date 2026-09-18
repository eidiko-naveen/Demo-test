import logging
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.memory.base import BaseMemoryManager
from app.memory.factory import MemoryFactory
from app.schemas.chat import ChatRequest
from app.schemas.response import AgentResponse


logger = logging.getLogger("enterprise_rag")


class ChatService:
    """
    Application service responsible for:

    1. Agent selection
    2. Memory loading
    3. Agent execution
    4. Memory persistence
    5. Conversation isolation
    """

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        *,
        checkpointer: Any | None = None,
        embeddings: Any | None = None,
        window_size: int = 10,
        **kwargs: Any,
    ):
        self.agent_provider = agent_provider
        self.checkpointer = checkpointer
        self.embeddings = embeddings
        self.window_size = window_size

        # Reuse stateful memory managers during the application lifetime.
        #
        # Key:
        #     memory mode + tenant + user + conversation
        #
        # This prevents managers such as semantic, episodic and procedural
        # memory from losing their state after every request.
        self._memory_managers: dict[
            tuple[str, str, str, str],
            BaseMemoryManager,
        ] = {}

    def _memory_key(
        self,
        *,
        mode: str,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> tuple[str, str, str, str]:
        return (
            mode,
            tenant_id,
            user_id,
            conversation_id,
        )

    def _get_memory_manager(
        self,
        *,
        mode: str,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> BaseMemoryManager:

        normalized_mode = MemoryFactory.normalize_mode(
            mode
        )

        key = self._memory_key(
            mode=normalized_mode,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        manager = self._memory_managers.get(key)

        if manager is None:
            manager = MemoryFactory.create(
                normalized_mode,
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                window_size=self.window_size,
                checkpointer=self.checkpointer,
                embeddings=self.embeddings,
            )

            self._memory_managers[key] = manager

        return manager

    async def chat(
        self,
        request: ChatRequest,
        *,
        tenant_id: str = "development-tenant",
        user_id: str = "development-user",
    ) -> AgentResponse:

        conversation_id = (
            request.conversation_id
            or str(uuid4())
        )

        memory_mode = MemoryFactory.normalize_mode(
            request.memory_mode
        )

        if not MemoryFactory.is_supported(
            memory_mode
        ):
            raise ValueError(
                f"Unsupported memory mode: {request.memory_mode}"
            )

        agent = self.agent_provider(
            request.agent_type
        )

        memory_manager: BaseMemoryManager | None = None
        conversation_context: list[
            dict[str, Any]
        ] = []

        if memory_mode != "none":
            memory_manager = self._get_memory_manager(
                mode=memory_mode,
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )

            try:
                conversation_context = (
                    memory_manager.load_context(
                        query=request.query
                    )
                )

            except Exception as exc:
                logger.warning(
                    "Memory load failed for mode=%s "
                    "tenant=%s user=%s conversation=%s: %s",
                    memory_mode,
                    tenant_id,
                    user_id,
                    conversation_id,
                    exc,
                )

                conversation_context = []

        agent_kwargs: dict[str, Any] = {
            "memory_mode": memory_mode,
            "conversation_id": conversation_id,
            "conversation_context": conversation_context,
        }

        normalized_agent = (
            request.agent_type
            .lower()
            .strip()
        )

        if normalized_agent in {
            "rag",
            "rag_agent",
            "hybrid",
            "hybrid_agent",
        }:
            agent_kwargs.update(
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            )
        else:
            agent_kwargs.update(
                limit=request.top_k
            )

        response = await agent.run(
            request.query,
            **agent_kwargs,
        )

        # Always return the generated conversation ID.
        response.conversation_id = conversation_id
        response.memory_mode = memory_mode

        if (
            memory_manager is not None
            and response.answer
        ):
            try:
                memory_manager.save_turn(
                    request.query,
                    response.answer,
                )

            except Exception as exc:
                logger.warning(
                    "Memory save failed for mode=%s "
                    "tenant=%s user=%s conversation=%s: %s",
                    memory_mode,
                    tenant_id,
                    user_id,
                    conversation_id,
                    exc,
                )

        return response

    def clear_memory(
        self,
        *,
        mode: str,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
    ) -> None:

        normalized_mode = MemoryFactory.normalize_mode(
            mode
        )

        key = self._memory_key(
            mode=normalized_mode,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        manager = self._memory_managers.pop(
            key,
            None,
        )

        if manager is not None:
            manager.clear()