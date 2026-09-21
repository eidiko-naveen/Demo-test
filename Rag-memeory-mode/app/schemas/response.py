from typing import Any

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    document_name: str
    page_number: int | None = None
    source: str | None = None
    score: float | None = None


class AgentResponse(BaseModel):
    answer: str
    agent_type: str
    memory_mode: str
    sources: list[SourceReference] = Field(default_factory=list)
    confidence: float | None = None
    used_rag: bool = False
    used_research: bool = False
    conversation_id: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
