"""
Entity Memory — extracts structured facts (names, preferences, dates, etc.)
from each turn using Claude's tool-forcing, and stores them as key/value
pairs per session. Good for recalling specific facts precisely rather than
vague "gist" recall like Summary mode.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import Entity
from src.db.session import get_db_session
from src.llm.claude_client import get_claude_client
from src.memory.base import MemoryStrategy

logger = structlog.get_logger()

ENTITY_SYSTEM_PROMPT = (
    "Extract any concrete facts, entities, or preferences mentioned in this "
    "message that would be useful to remember for later in the conversation "
    "(e.g. names, dates, preferences, decisions, constraints). If nothing "
    "worth remembering is present, return an empty list."
)

ENTITY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short label for the fact, e.g. 'favorite_language'"},
                    "value": {"type": "string", "description": "The fact's value, e.g. 'Python'"},
                },
                "required": ["name", "value"],
            },
        }
    },
    "required": ["facts"],
}


class EntityMemory(MemoryStrategy):
    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        if role != "user":
            return  # only extract facts from user messages, not the assistant's own replies

        claude = get_claude_client()
        result = await claude.extract_structured(
            system=ENTITY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tool_name="record_facts",
            tool_schema=ENTITY_TOOL_SCHEMA,
            max_tokens=512,
        )

        facts = result.get("facts", [])
        if not facts:
            return

        async with get_db_session() as db:
            for fact in facts:
                stmt = (
                    pg_insert(Entity)
                    .values(session_id=session_id, entity_name=fact["name"], entity_value=fact["value"])
                    .on_conflict_do_update(
                        index_elements=["session_id", "entity_name"],
                        set_={"entity_value": fact["value"]},
                    )
                )
                await db.execute(stmt)

    async def get_context(self, session_id: str, query: str) -> str:
        async with get_db_session() as db:
            result = await db.execute(select(Entity).where(Entity.session_id == session_id))
            entities = result.scalars().all()

        if not entities:
            return ""

        lines = [f"- {e.entity_name}: {e.entity_value}" for e in entities]
        return "Known facts about this conversation:\n" + "\n".join(lines)