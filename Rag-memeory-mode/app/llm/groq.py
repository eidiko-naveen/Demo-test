from app.utils.exceptions import ConfigurationError, LLMError


class GroqProvider:
    def __init__(self, *, api_key: str | None, model: str):
        if not api_key:
            raise ConfigurationError("GROQ_API_KEY is required for the Groq provider")
        from langchain_groq import ChatGroq

        self._model = ChatGroq(model=model, api_key=api_key)

    async def ainvoke(self, messages: list[dict[str, str]]) -> str:
        try:
            response = await self._model.ainvoke(messages)
            content = response.content
            return content if isinstance(content, str) else str(content)
        except Exception as exc:
            raise LLMError("The language model request failed") from exc
