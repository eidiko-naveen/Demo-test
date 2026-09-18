"""
Summary Memory — instead of keeping every raw turn, maintains one running
LLM-generated summary per session. Best for long conversations where token
cost/context length matters more than exact recall of every message.
"""
import structlog
from sqlalchemy import select

from src.db.models import ConversationSummary
from src.db.session import get_db_session
from src.llm.claude_client import get_claude_client
from src.memory.base import MemoryStrategy

logger = structlog.get_logger()

SUMMARY_SYSTEM_PROMPT = (
    "You maintain a running summary of a conversation. Given the existing "
    "summary and a new turn, produce an updated summary that incorporates "
    "the new information. Keep it concise (3-5 sentences max), factual, "
    "and written in third person. Do not add commentary — output only the "
    "updated summary text."
)


class SummaryMemory(MemoryStrategy):
    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        async with get_db_session() as db:
            existing = await db.get(ConversationSummary, session_id)
            current_summary = existing.summary_text if existing else "(no prior summary)"

            claude = get_claude_client()
            updated_summary = await claude.generate(
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Existing summary: {current_summary}\n\n"
                            f"New turn ({role}): {content}\n\n"
                            "Updated summary:"
                        ),
                    }
                ],
                max_tokens=256,
            )

            if existing:
                existing.summary_text = updated_summary
            else:
                db.add(ConversationSummary(session_id=session_id, summary_text=updated_summary))

    async def get_context(self, session_id: str, query: str) -> str:
        async with get_db_session() as db:
            result = await db.execute(
                select(ConversationSummary).where(ConversationSummary.session_id == session_id)
            )
            summary = result.scalar_one_or_none()

        if not summary or not summary.summary_text:
            return ""

        return f"Conversation summary so far: {summary.summary_text}"