"""
Persistent Memory — the only mode that survives across SESSIONS, not just
within one. Keyed by user_id instead of session_id, so if the same user
starts a brand new chat session tomorrow, relevant facts from previous
sessions are still recalled. This is what "long-term memory" means as
opposed to Buffer/Vector/Entity/Summary, which all reset per session.
"""
import structlog
from sqlalchemy import select

from src.db.models import UserMemory
from src.db.session import get_db_session
from src.memory.base import MemoryStrategy
from src.rag.retriever import embed_text

logger = structlog.get_logger()

TOP_K = 5


class PersistentMemory(MemoryStrategy):
    """
    Note: add_turn/get_context take session_id per the MemoryStrategy
    interface, but this mode internally resolves it to a user_id so
    recall works across sessions. For this project, user_id == session_id's
    prefix before the first ':' (see _resolve_user_id) — a real multi-user
    system would pass a proper authenticated user_id instead.
    """

    def _resolve_user_id(self, session_id: str) -> str:
        return session_id.split(":", 1)[0] if ":" in session_id else session_id

    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        if role != "user":
            return  # only persist things the user said, not the assistant's replies

        user_id = self._resolve_user_id(session_id)
        embedding = await embed_text(content)

        async with get_db_session() as db:
            db.add(
                UserMemory(
                    user_id=user_id,
                    session_id=session_id,
                    key_fact=content,
                    embedding=embedding,
                )
            )

    async def get_context(self, session_id: str, query: str) -> str:
        user_id = self._resolve_user_id(session_id)
        query_embedding = await embed_text(query)

        async with get_db_session() as db:
            result = await db.execute(
                select(UserMemory)
                .where(UserMemory.user_id == user_id)
                .order_by(UserMemory.embedding.cosine_distance(query_embedding))
                .limit(TOP_K)
            )
            memories = result.scalars().all()

        if not memories:
            return ""

        lines = [f"- {m.key_fact}" for m in memories]
        return "Things this user has shared in past sessions:\n" + "\n".join(lines)