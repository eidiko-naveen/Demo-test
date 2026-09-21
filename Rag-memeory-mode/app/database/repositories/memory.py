from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_user(
        self, *, tenant_id: str, user_id: str, memory_type: str | None = None
    ) -> Sequence[Memory]:
        statement = select(Memory).where(
            Memory.tenant_id == tenant_id,
            Memory.user_id == user_id,
        )
        if memory_type is not None:
            statement = statement.where(Memory.memory_type == memory_type)
        return (await self.session.scalars(statement)).all()
