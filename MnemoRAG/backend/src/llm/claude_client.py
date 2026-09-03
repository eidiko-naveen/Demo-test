"""
Thin wrapper — now backed by Groq instead of Claude, but keeps the same
interface (get_claude_client, .generate, .extract_structured) so nothing
else in the codebase needs to change.
"""
import json
from functools import lru_cache

import structlog
from groq import APIConnectionError, APIStatusError, AsyncGroq, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import get_settings

logger = structlog.get_logger()

_RETRYABLE = (RateLimitError, APIConnectionError, APIStatusError)


class ClaudeClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._model = settings.groq_model

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def extract_structured(
        self,
        system: str,
        messages: list[dict],
        tool_name: str,
        tool_schema: dict,
        max_tokens: int = 1024,
    ) -> dict:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"Return data via {tool_name}.",
                        "parameters": tool_schema,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            logger.warning("groq_no_tool_call", tool_name=tool_name)
            return {}
        return json.loads(tool_calls[0].function.arguments)


@lru_cache
def get_claude_client() -> ClaudeClient:
    return ClaudeClient()