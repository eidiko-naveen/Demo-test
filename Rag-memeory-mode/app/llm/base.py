from typing import Protocol


class LLMProvider(Protocol):
    async def ainvoke(self, messages: list[dict[str, str]]) -> str: ...
