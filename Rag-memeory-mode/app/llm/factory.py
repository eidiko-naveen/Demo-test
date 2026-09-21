from app.config.settings import Settings
from app.llm.base import LLMProvider
from app.llm.groq import GroqProvider


class LLMFactory:
    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        return GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)
