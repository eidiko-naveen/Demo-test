from typing import Any, Literal, TypedDict


AgentType = Literal[
    "rag",
    "research",
    "hybrid",
]

MemoryMode = Literal[
    "none",
    "short_term",
    "checkpoint",
    "long_term",
    "cross_thread",
    "semantic",
    "episodic",
    "procedural",
    "persistent_db",
]

RouteType = Literal[
    "rag",
    "research",
    "hybrid",
]


class AgentState(TypedDict, total=False):
    user_id: str
    tenant_id: str
    conversation_id: str
    session_id: str

    query: str

    messages: list[dict[str, Any]]

    memory_mode: MemoryMode
    memory_window_size: int

    agent_type: AgentType
    route: RouteType

    conversation_context: list[
        dict[str, Any]
    ]

    retrieved_documents: list[
        dict[str, Any]
    ]

    research_results: list[
        dict[str, Any]
    ]

    sources: list[
        dict[str, Any]
    ]

    tool_results: list[
        dict[str, Any]
    ]

    intermediate_steps: list[
        dict[str, Any]
    ]

    final_answer: str

    errors: list[str]

    metadata: dict[str, Any]

    # Runtime dependencies used by graph memory.
    checkpointer: Any
    embeddings: Any