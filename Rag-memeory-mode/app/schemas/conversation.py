from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=255)
    agent_type: str = "rag"
    memory_mode: str = "none"


class ConversationResponse(BaseModel):
    id: str
    title: str
    agent_type: str
    memory_mode: str
    archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
