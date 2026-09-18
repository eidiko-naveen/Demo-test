from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        title: str,
        agent_type: str,
        memory_mode: str,
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            agent_type=agent_type,
            memory_mode=memory_mode,
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get(self, *, tenant_id: str, user_id: str, conversation_id: str) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
        )
        return await self.session.scalar(statement)

    async def list(self, *, tenant_id: str, user_id: str) -> Sequence[Conversation]:
        statement = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.archived.is_(False),
            )
            .order_by(Conversation.updated_at.desc())
        )
        return (await self.session.scalars(statement)).all()

    async def archive(self, *, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        statement = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
            .values(archived=True)
        )
        result = await self.session.execute(statement)
        await self.session.commit()
        return bool(result.rowcount)


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> Message:
        message = Message(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources or [],
            metadata_json=metadata or {},
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def list_for_conversation(
        self, *, tenant_id: str, user_id: str, conversation_id: str
    ) -> Sequence[Message]:
        statement = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
        )
        return (await self.session.scalars(statement)).all()
