from pydantic import BaseModel
from typing import Any, Optional


class AgentInput(BaseModel):
    query: str
    context: Optional[dict[str, Any]] = None


class AgentOutput(BaseModel):
    result: str
    metadata: Optional[dict[str, Any]] = None
    success: bool = True
    error: Optional[str] = None


class ModelConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-3.5-flash-lite"


class AgentSpec(BaseModel):
    name: str
    description: str
    capabilities: list[str]
    tools: list[str] = []
    model: ModelConfig = ModelConfig()
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    system_prompt: str


PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "models": [
            {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash"},
            {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash"},
            {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash Lite"},
        ]
    },
    "groq": {
        "label": "Groq",
        "models": [
            {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B"},
            {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B"},
            {"id": "openai/gpt-oss-120b", "label": "GPT-OSS 120B"},
        ]
    },
    "anthropic": {
        "label": "Anthropic",
        "models": [
            {"id": "claude-opus-4-6", "label": "Claude Opus 4.6"},
            {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ]
    }
}