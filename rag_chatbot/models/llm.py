from functools import lru_cache
from typing import Any

from langfuse import Langfuse

from config.settings import get_settings

try:
    from llama_index.core import Settings as LlamaSettings
except Exception:  # pragma: no cover - only used in runtime paths
    LlamaSettings = None

try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
except Exception:  # pragma: no cover - deferred until model is needed
    HuggingFaceEmbedding = None

try:
    from llama_index.llms.groq import Groq
except Exception:  # pragma: no cover - deferred until model is needed
    Groq = None


@lru_cache(maxsize=1)
def get_langfuse() -> Langfuse | None:

    settings = get_settings()

    if not (
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):

        return None

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        tracing_enabled=True,
    )


class TracedLLM:

    def __init__(self, llm):
        self._llm = llm

    def complete(self, prompt: str, **kwargs: Any):
        langfuse = get_langfuse()
        if langfuse is None:
            return self._llm.complete(prompt, **kwargs)
        with langfuse.start_as_current_observation(
            name="llm-completion",
            as_type="generation",
            input=prompt if get_settings().langfuse_capture_content else {"content_captured": False},
            model=getattr(self._llm, "model", "configured-model"),
        ) as generation:
            try:
                response = self._llm.complete(prompt, **kwargs)
                generation.update(output=response.text if get_settings().langfuse_capture_content else {"content_captured": False})
                return response
            except Exception as exc:
                generation.update(level="ERROR", status_message=type(exc).__name__)
                raise


@lru_cache(maxsize=1)
def get_llm():

    settings = get_settings()

    settings.validate_runtime()
    if settings.llm_provider != "groq":
        raise ValueError("Only the Groq provider is enabled for this deployment")
    if Groq is None:
        raise ImportError("llama-index-llms-groq is not installed or importable")
    return TracedLLM(Groq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    ))


@lru_cache(maxsize=1)
def get_embed_model():

    settings = get_settings()

    if HuggingFaceEmbedding is None:
        raise ImportError("llama-index-embeddings-huggingface is not installed or importable")
    return HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )


def configure_llamaindex():

    if LlamaSettings is None:
        raise ImportError("llama-index-core is not installed or importable")
    LlamaSettings.llm = get_llm()
    LlamaSettings.embed_model = get_embed_model()