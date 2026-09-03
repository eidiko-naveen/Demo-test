"""
The two functional endpoints: /chat (RAG + memory + Claude) and /ingest
(add documents to the knowledge base). This is where memory/factory.py,
rag/retriever.py, and llm/claude_client.py all come together per-request.
"""
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config import get_settings
from src.llm.claude_client import get_claude_client
from src.memory.factory import available_modes, get_memory_strategy
from src.rag.ingest import ingest_document
from src.rag.retriever import retrieve_relevant_chunks

logger = structlog.get_logger()

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Use 'user_id:session_id' format for Persistent mode to work correctly")
    message: str
    memory_mode: str | None = Field(None, description="Defaults to DEFAULT_MEMORY_MODE if omitted")


class ChatResponse(BaseModel):
    reply: str
    memory_mode: str
    memory_context_used: str
    rag_chunks_used: list[str]


class IngestRequest(BaseModel):
    source: str
    text: str


class IngestResponse(BaseModel):
    chunks_stored: int


CHAT_SYSTEM_PROMPT = (
    "You are MnemoRAG, a helpful assistant with access to a knowledge base "
    "and conversation memory. Use the provided context to answer accurately. "
    "If the context doesn't contain the answer, say so rather than guessing."
)


@router.get("/memory-modes")
async def list_memory_modes() -> dict:
    """Backs the Streamlit sidebar dropdown — one source of truth, no hardcoded list in the frontend."""
    return {"modes": available_modes()}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    mode = request.memory_mode or get_settings().default_memory_mode

    try:
        strategy = get_memory_strategy(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 1. Gather context: RAG documents + conversation memory, independently
    rag_chunks = await retrieve_relevant_chunks(request.message)
    memory_context = await strategy.get_context(request.session_id, request.message)

    # 2. Build the prompt
    context_parts = []
    if rag_chunks:
        context_parts.append("Knowledge base context:\n" + "\n---\n".join(rag_chunks))
    if memory_context:
        context_parts.append(memory_context)
    full_context = "\n\n".join(context_parts) if context_parts else "(no context available)"

    user_prompt = f"{full_context}\n\nUser question: {request.message}"

    # 3. Call Claude
    claude = get_claude_client()
    reply = await claude.generate(
        system=CHAT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # 4. Persist this turn to memory (user message + assistant reply)
    await strategy.add_turn(request.session_id, "user", request.message)
    await strategy.add_turn(request.session_id, "assistant", reply)

    return ChatResponse(
        reply=reply,
        memory_mode=mode,
        memory_context_used=memory_context or "(none)",
        rag_chunks_used=rag_chunks,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    chunks_stored = await ingest_document(request.source, request.text)
    return IngestResponse(chunks_stored=chunks_stored)