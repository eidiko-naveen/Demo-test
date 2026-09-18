"""
Vector (Semantic) Memory — instead of "last N turns" (Buffer) or a running
summary, retrieves the K most semantically relevant past turns to the
CURRENT query. Good when a conversation is long and non-linear — the user
might reference something from 50 messages ago, and Buffer's fixed window
would miss it entirely.
"""
import structlog
from sqlalchemy import select

from src.db.models import ConversationTurn
from src.db.session import get_db_session
from src.memory.base import MemoryStrategy
from src.rag.retriever import embed_text

logger = structlog.get_logger()

TOP_K = 5


class VectorMemory(MemoryStrategy):
    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        embedding = await embed_text(content)
        async with get_db_session() as db:
            db.add(ConversationTurn(session_id=session_id, role=role, content=content, embedding=embedding))

    async def get_context(self, session_id: str, query: str) -> str:
        query_embedding = await embed_text(query)

        async with get_db_session() as db:
            result = await db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.embedding.cosine_distance(query_embedding))
                .limit(TOP_K)
            )
            turns = result.scalars().all()

        if not turns:
            return ""

        # Re-sort by recency for readability, even though retrieval was by relevance
        turns_sorted = sorted(turns, key=lambda t: t.created_at)
        lines = [f"{t.role}: {t.content}" for t in turns_sorted]
        return "Relevant past exchanges:\n" + "\n".join(lines)