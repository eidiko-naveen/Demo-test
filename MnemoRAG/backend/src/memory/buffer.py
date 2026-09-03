"""
Buffer Memory — the simplest mode: just the last N raw turns, no embeddings,
no LLM calls. Cheapest and fastest mode; good baseline / fallback.
"""
import structlog
from sqlalchemy import select

from src.config import get_settings
from src.db.models import ConversationTurn
from src.db.session import get_db_session
from src.memory.base import MemoryStrategy
from src.rag.retriever import embed_text

logger = structlog.get_logger()


class BufferMemory(MemoryStrategy):
    def __init__(self) -> None:
        self._window = get_settings().buffer_window_size

    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        embedding = await embed_text(content)  # stored for reuse by Vector/Hybrid modes on the same table
        async with get_db_session() as db:
            db.add(ConversationTurn(session_id=session_id, role=role, content=content, embedding=embedding))

    async def get_context(self, session_id: str, query: str) -> str:
        async with get_db_session() as db:
            result = await db.execute(
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.created_at.desc())
                .limit(self._window)
            )
            turns = list(reversed(result.scalars().all()))

        if not turns:
            return ""

        lines = [f"{t.role}: {t.content}" for t in turns]
        return "Recent conversation:\n" + "\n".join(lines)