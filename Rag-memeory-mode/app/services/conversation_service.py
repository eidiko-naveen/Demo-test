from app.database.repositories.conversations import ConversationRepository
from app.schemas.conversation import ConversationCreateRequest, ConversationResponse
from app.security.auth import UserContext


class ConversationService:
    def __init__(self, repository: ConversationRepository, context: UserContext):
        self.repository = repository
        self.context = context

    async def create_for_current_user(
        self, payload: ConversationCreateRequest
    ) -> ConversationResponse:
        conversation = await self.repository.create(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            title=payload.title,
            agent_type=payload.agent_type,
            memory_mode=payload.memory_mode,
        )
        return self._response(conversation)

    async def list_for_current_user(self) -> list[ConversationResponse]:
        conversations = await self.repository.list(
            tenant_id=self.context.tenant_id, user_id=self.context.user_id
        )
        return [self._response(conversation) for conversation in conversations]

    async def get_for_current_user(self, conversation_id: str) -> ConversationResponse | None:
        conversation = await self.repository.get(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=conversation_id,
        )
        return self._response(conversation) if conversation else None

    async def archive(self, conversation_id: str) -> bool:
        return await self.repository.archive(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=conversation_id,
        )

    @staticmethod
    def _response(conversation: object) -> ConversationResponse:
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            agent_type=conversation.agent_type,
            memory_mode=conversation.memory_mode,
            archived=conversation.archived,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
