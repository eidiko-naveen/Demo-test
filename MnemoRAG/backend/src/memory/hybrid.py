"""
Hybrid Memory — combines Buffer's recency (last N turns, guaranteed
continuity) with Vector's relevance (semantically similar turns from
anywhere in the session history). This is the "best of both worlds" mode:
Buffer alone can miss something said 50 messages ago; Vector alone can miss
the immediate flow of the last exchange. Hybrid covers both gaps.
"""
import structlog
from sqlalchemy import select

from src.config import get_settings
from src.db.models import ConversationTurn
from src.db.session import get_db_session
from src.memory.base import MemoryStrategy
from src.rag.retriever import embed_text

logger = structlog.get_logger()

VECTOR_TOP_K = 3


class HybridMemory(MemoryStrategy):
    def __init__(self) -> None:
        self._window = get_settings().buffer_window_size

    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        embedding = await embed_text(content)
        async with get_db_session() as db:
            db.add(ConversationTurn(session_id=session_id, role=role, content=content, embedding=embedding))

    async def get_context(self, session_id: str, query: str) -> str:
        async with get_db_session() as db:
            # Recency: last N turns (same as Buffer)
            recent_result = await db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.created_at.desc())
                .limit(self._window)
            )
            recent_turns = list(reversed(recent_result.scalars().all()))
            recent_ids = {t.id for t in recent_turns}

            # Relevance: top-K similar turns NOT already in the recent window
            query_embedding = await embed_text(query)
            similar_result = await db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.embedding.cosine_distance(query_embedding))
                .limit(self._window + VECTOR_TOP_K)  # over-fetch, then filter dupes below
            )
            similar_turns = [t for t in similar_result.scalars().all() if t.id not in recent_ids][:VECTOR_TOP_K]

        if not recent_turns and not similar_turns:
            return ""

        parts = []
        if similar_turns:
            similar_sorted = sorted(similar_turns, key=lambda t: t.created_at)
            parts.append("Relevant earlier context:\n" + "\n".join(f"{t.role}: {t.content}" for t in similar_sorted))
        if recent_turns:
            parts.append("Most recent exchange:\n" + "\n".join(f"{t.role}: {t.content}" for t in recent_turns))

        return "\n\n".join(parts)