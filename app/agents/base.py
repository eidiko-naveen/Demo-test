from typing import Protocol

from app.schemas.response import AgentResponse


class Agent(Protocol):
    async def run(self, query: str, **kwargs: object) -> AgentResponse: ...
