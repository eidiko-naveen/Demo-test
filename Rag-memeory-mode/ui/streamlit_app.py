import os
import re
from datetime import datetime, timezone
from typing import Any

import requests
import streamlit as st

# Application Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1").rstrip("/")
USER_HEADERS = {
    "X-User-Id": os.getenv("MOCK_USER_ID", "development-user"),
    "X-Tenant-Id": os.getenv("MOCK_TENANT_ID", "development-tenant"),
}

AGENTS = {
    "Hybrid Intelligence": "hybrid",
    "Enterprise RAG Agent": "rag",
    "Deep Research Agent": "research",
}

AGENT_DESCRIPTIONS = {
    "hybrid": "Synthesizes internal enterprise knowledge with live external web research.",
    "rag": "Strictly grounded in your ingested enterprise documents and vector database.",
    "research": "Performs live external web queries and extracts relevant industry findings.",
}

MEMORIES = {
    "Short-term / Thread Memory": "short_term",
    "Checkpoint Memory": "checkpoint",
    "Long-term Memory": "long_term",
    "Cross-thread Memory": "cross_thread",
    "Semantic Memory": "semantic",
    "Episodic Memory": "episodic",
    "Procedural Memory": "procedural",
    "Persistent Database-backed Memory": "persistent_db",
    "Stateless (No Memory)": "none",
}

MEMORY_DESCRIPTIONS = {
    "short_term": "Thread-scoped sliding-window chat history powered by LangChain InMemoryChatMessageHistory.",
    "checkpoint": "State checkpointing and time-travel replay powered by LangGraph MemorySaver.",
    "long_term": "User-scoped persistent knowledge that transcends individual chat sessions.",
    "cross_thread": "Tenant-scoped shared knowledge pool accessible across multiple conversation threads.",
    "semantic": "Vector-embedded semantic memory with cosine similarity contextual retrieval.",
    "episodic": "Chronological situation-action-outcome episode store capturing interaction history.",
    "procedural": "Standard operating procedures and behavioral rules governing agent operations.",
    "persistent_db": "Durable relational database-backed chat memory with ACID transactions.",
    "none": "Single-turn stateless mode with zero context retention.",
}

MEMORY_TEST_PROMPTS = {
    "short_term": "Remember that my favorite framework is LangChain and ask me later what I prefer.",
    "checkpoint": "I am testing checkpoint memory. Please remember that the project is using LangGraph state replay.",
    "long_term": "My name is yash and I work in eidiko. Please remember this for future conversations.",
    "cross_thread": "This is a tenant-wide note: our shared infra is server.corp.internal.",
    "semantic": "What are the deployment notes for AWS EKS and Terraform in this project?",
    "episodic": "During the last incident, we had a database CPU spike and we indexed queries to reduce latency.",
    "procedural": "Always verify enterprise claims against documentation before answering conclusively.",
    "persistent_db": "Store this in durable memory: our default release process is deployment-first then validation.",
    "none": "Use stateless mode and do not retain any context from this turn.",
}

MEMORY_TEST_MATRIX = {
    "short_term": {
        "prompt": MEMORY_TEST_PROMPTS["short_term"],
        "expectation": "Context is retained only within the current conversation thread.",
    },
    "checkpoint": {
        "prompt": MEMORY_TEST_PROMPTS["checkpoint"],
        "expectation": "State survives between turns and supports replay-like checkpoint behavior.",
    },
    "long_term": {
        "prompt": MEMORY_TEST_PROMPTS["long_term"],
        "expectation": "The name/profile persists across conversations for the same user.",
    },
    "cross_thread": {
        "prompt": MEMORY_TEST_PROMPTS["cross_thread"],
        "expectation": "Tenant-scoped facts are visible across separate threads in the same tenant.",
    },
    "semantic": {
        "prompt": MEMORY_TEST_PROMPTS["semantic"],
        "expectation": "Relevant historical turns are surfaced using semantic similarity.",
    },
    "episodic": {
        "prompt": MEMORY_TEST_PROMPTS["episodic"],
        "expectation": "A structured past episode is surfaced with situation/action/outcome context.",
    },
    "procedural": {
        "prompt": MEMORY_TEST_PROMPTS["procedural"],
        "expectation": "The agent follows operational rules and retains the directive in memory.",
    },
    "persistent_db": {
        "prompt": MEMORY_TEST_PROMPTS["persistent_db"],
        "expectation": "The fact persists in the durable database-backed memory store.",
    },
    "none": {
        "prompt": MEMORY_TEST_PROMPTS["none"],
        "expectation": "No context is retained between turns; this is stateless mode.",
    },
}

# Page Configuration
st.set_page_config(
    page_title="Enterprise Knowledge Intelligence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Responsive Enterprise Styling (Dark / Glassmorphic Aesthetic)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --bg-dark: #090d16;
        --card-bg: rgba(17, 24, 39, 0.75);
        --card-border: rgba(255, 255, 255, 0.08);
        --accent-blue: #3b82f6;
        --accent-purple: #6366f1;
        --accent-teal: #0ea5e9;
        --accent-emerald: #10b981;
        --text-primary: #f3f4f6;
        --text-muted: #9ca3af;
        --radius: 12px;
    }

    .stApp {
        background: radial-gradient(circle at 10% 10%, rgba(59, 130, 246, 0.12) 0%, transparent 40%),
                    radial-gradient(circle at 90% 90%, rgba(99, 102, 241, 0.10) 0%, transparent 45%),
                    #090d16;
        color: var(--text-primary);
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    [data-testid="stSidebar"] {
        background: rgba(11, 15, 25, 0.95);
        border-right: 1px solid var(--card-border);
        backdrop-filter: blur(20px);
    }

    [data-testid="stSidebar"] .block-container {
        padding: 1.5rem 1.25rem;
    }

    h1, h2, h3, h4 {
        font-family: 'Space Grotesk', sans-serif;
        color: #ffffff;
        letter-spacing: -0.02em;
    }

    p, span, label, div {
        color: var(--text-primary);
    }

    /* Brand Header */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 0.85rem;
        padding-bottom: 1.25rem;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid var(--card-border);
    }

    .brand-icon {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #3b82f6, #6366f1);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.35);
    }

    .brand-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.2rem;
        font-weight: 700;
        color: #ffffff;
        margin: 0;
        line-height: 1.2;
    }

    .brand-subtitle {
        font-size: 0.72rem;
        color: var(--accent-teal);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 600;
    }

    /* Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: rgba(15, 23, 42, 0.6);
    }

    .dot-live {
        width: 7px;
        height: 7px;
        background-color: var(--accent-emerald);
        border-radius: 50%;
        box-shadow: 0 0 8px var(--accent-emerald);
    }

    .dot-warn {
        width: 7px;
        height: 7px;
        background-color: #f59e0b;
        border-radius: 50%;
        box-shadow: 0 0 8px #f59e0b;
    }

    /* Hero Banner */
    .hero-banner {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%);
        border: 1px solid var(--card-border);
        border-left: 4px solid var(--accent-blue);
        border-radius: var(--radius);
        padding: 1.75rem 2rem;
        margin-bottom: 1.75rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(16px);
    }

    .hero-banner h1 {
        font-size: clamp(1.4rem, 2.8vw, 2.2rem);
        margin: 0 0 0.5rem 0;
        background: linear-gradient(90deg, #ffffff, #93c5fd);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero-banner p {
        color: var(--text-muted);
        font-size: 0.95rem;
        margin: 0;
        max-width: 750px;
    }

    /* Chat Messages */
    [data-testid="stChatMessage"] {
        background: rgba(17, 24, 39, 0.8) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 14px !important;
        padding: 1rem 1.25rem !important;
        margin-bottom: 1rem !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
    }

    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
        color: #f3f4f6 !important;
        font-size: 0.95rem;
        line-height: 1.6;
    }

    /* Citation Card */
    .citation-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 8px;
        padding: 0.6rem 0.85rem;
        margin-top: 0.45rem;
        font-size: 0.82rem;
    }

    .citation-title {
        font-weight: 600;
        color: #60a5fa;
    }

    .citation-snippet {
        color: #94a3b8;
        font-size: 0.78rem;
        margin-top: 0.2rem;
    }

    /* Buttons & Inputs */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6, #4f46e5) !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
    }

    .stButton > button[kind="primary"]:hover {
        opacity: 0.95;
        transform: translateY(-1px);
    }

    [data-testid="stChatInput"] {
        border-radius: 12px;
        border: 1px solid rgba(59, 130, 246, 0.3) !important;
        background: rgba(15, 23, 42, 0.9) !important;
    }

    /* Quick Prompt Chips */
    .chip-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin: 1rem 0;
    }

    .prompt-chip {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 20px;
        padding: 0.35rem 0.8rem;
        font-size: 0.82rem;
        color: #cbd5e1;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .prompt-chip:hover {
        background: rgba(59, 130, 246, 0.2);
        border-color: rgba(59, 130, 246, 0.4);
        color: #ffffff;
    }

    /* Mobile adjustments */
    @media (max-width: 768px) {
        .hero-banner { padding: 1.25rem; }
        [data-testid="stSidebar"] { min-width: 100%; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    headers = dict(USER_HEADERS)
    headers.update(kwargs.pop("headers", {}))
    return requests.request(method, f"{API_URL}{path}", headers=headers, timeout=60, **kwargs)


@st.cache_data(ttl=5)
def fetch_system_health() -> dict[str, Any]:
    try:
        response = api_request("GET", "/health")
        return response.json() if response.ok else {"status": "offline"}
    except requests.RequestException:
        return {"status": "offline"}


def fetch_documents() -> list[dict[str, Any]]:
    try:
        response = api_request("GET", "/documents")
        return response.json() if response.ok else []
    except requests.RequestException:
        return []


# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "input_query" not in st.session_state:
    st.session_state.input_query = ""
if "memory_test_prompt" not in st.session_state:
    st.session_state.memory_test_prompt = ""
if "memory_snapshot" not in st.session_state:
    st.session_state.memory_snapshot = {}

# Sidebar: Controls & System State
with st.sidebar:
    st.markdown(
        """
        <div class="brand-container">
            <div class="brand-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
            </div>
            <div>
                <div class="brand-title">Enterprise RAG</div>
                <div class="brand-subtitle">Intelligence Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Health Check Indicator
    health = fetch_system_health()
    status = health.get("status", "offline")
    if status == "healthy":
        st.markdown(
            '<div class="status-badge"><div class="dot-live"></div><span>Platform Operational</span></div>',
            unsafe_allow_html=True,
        )
    elif status == "degraded":
        st.markdown(
            '<div class="status-badge"><div class="dot-warn"></div><span>App Ready (Standalone Mode)</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge"><div class="dot-warn"></div><span>Backend Reconnecting...</span></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    if st.button("＋  New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_id = None
        st.rerun()

    st.divider()

    # Agent Selection
    st.markdown("#### 🤖 Agent Engine")
    agent_label = st.selectbox(
        "Select Agent",
        list(AGENTS),
        index=0,
        label_visibility="collapsed",
    )
    selected_agent = AGENTS[agent_label]
    st.caption(AGENT_DESCRIPTIONS[selected_agent])

    # Memory Mode Selection (LangChain & LangGraph Only)
    st.markdown("#### 💾 Memory Subsystem")
    memory_label = st.selectbox(
        "Select Memory Mode",
        list(MEMORIES),
        index=0,
        label_visibility="collapsed",
    )
    selected_memory = MEMORIES[memory_label]
    st.caption(MEMORY_DESCRIPTIONS[selected_memory])

    test_prompt = MEMORY_TEST_PROMPTS.get(selected_memory, "Remember this for future context.")
    st.info(f"Suggested test: {test_prompt}")
    if st.button("Use memory test prompt", use_container_width=True):
        st.session_state.input_query = test_prompt
        st.session_state.memory_test_prompt = test_prompt
        st.rerun()

    st.markdown("#### 🧠 Memory Test Matrix")
    for mode_name, details in MEMORY_TEST_MATRIX.items():
        mode_label = next((label for label, value in MEMORIES.items() if value == mode_name), mode_name)
        with st.expander(f"{mode_label}", expanded=(mode_name == selected_memory)):
            st.write(details["prompt"])
            st.caption(details["expectation"])

    st.markdown("#### 🧠 Memory State Preview")
    snapshot = st.session_state.memory_snapshot.get(selected_memory, {})
    if snapshot:
        st.caption(f"Last update: {snapshot.get('updated_at', 'unknown')}")
        st.write(f"Mode: {snapshot.get('mode', selected_memory)}")
        st.write(f"Tenant: {snapshot.get('tenant_id', USER_HEADERS.get('X-Tenant-Id'))}")
        st.write(f"User: {snapshot.get('user_id', USER_HEADERS.get('X-User-Id'))}")
        st.write(f"Turns stored: {snapshot.get('turn_count', 0)}")
        st.write(f"Last prompt: {snapshot.get('last_prompt', 'No prompt recorded')[:120]}")
        if snapshot.get("profile_name"):
            st.success(f"Profile hint: {snapshot['profile_name']}")
    else:
        st.caption("No memory activity yet for this mode.")
        if selected_memory == "none":
            st.caption("Stateless mode keeps no context between turns.")

    st.divider()

    # Knowledge Base / Document Upload
    st.markdown("#### 📂 Enterprise Knowledge Base")
    uploaded_files = st.file_uploader(
        "Upload Documents",
        type=["pdf", "docx", "txt", "md", "csv", "json"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded_files and st.button("Ingest Files", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        for idx, file in enumerate(uploaded_files):
            try:
                resp = api_request(
                    "POST",
                    "/documents/upload",
                    files={"file": (file.name, file.getvalue(), file.type)},
                )
                if resp.ok:
                    st.toast(f"✅ Ingested: {file.name}")
                else:
                    try:
                        err_msg = resp.json().get("detail", "Ingestion failed")
                    except Exception:
                        err_msg = resp.text or f"HTTP {resp.status_code}"
                    st.error(f"{file.name}: {err_msg}")
            except Exception as e:
                st.error(f"Error uploading {file.name}: {e}")
            progress_bar.progress((idx + 1) / len(uploaded_files))
        st.rerun()

    docs = fetch_documents()
    if docs:
        st.caption(f"📚 {len(docs)} Document(s) in Vector Index")
        with st.expander("View Indexed Documents"):
            for doc in docs:
                st.markdown(f"• **{doc.get('document_name')}**")
                st.caption(f"Type: {doc.get('document_type', 'txt').upper()} | ID: {doc.get('document_id', '')[:8]}...")
    else:
        st.caption("No documents ingested yet. Upload PDFs or Docs above.")


# Main View: Hero Banner & Workspace
st.markdown(
    """
    <div class="hero-banner">
        <h1>Enterprise Knowledge Intelligence</h1>
        <p>Grounded conversational AI with LangChain & LangGraph multi-mode memory architectures (Short-term, Checkpoint, Long-term, Cross-thread, Semantic, Episodic, Procedural, and Database) with real-time retrieval augmentation.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Render Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Render Sources / Citations if available
        sources = message.get("sources", [])
        if sources:
            with st.expander(f"🔍 Verified Sources ({len(sources)})", expanded=False):
                for src in sources:
                    doc_name = src.get("document_name") or src.get("source") or "Enterprise Knowledge Base"
                    score = src.get("score")
                    score_badge = f" • Score: {int(score * 100)}%" if score is not None else ""
                    snippet = src.get("snippet") or src.get("text") or ""
                    st.markdown(
                        f"""
                        <div class="citation-card">
                            <div class="citation-title">📄 {doc_name}{score_badge}</div>
                            {f'<div class="citation-snippet">{snippet[:220]}...</div>' if snippet else ''}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# Chat Input & Execution
if st.session_state.memory_test_prompt:
    st.caption(f"Memory test prompt loaded: {st.session_state.memory_test_prompt}")

prompt = st.chat_input("Ask a question about your documents or enterprise topics...", key="chat_input")
if prompt is None and st.session_state.input_query:
    prompt = st.session_state.input_query
    st.session_state.input_query = ""

if prompt:
    st.session_state.memory_test_prompt = ""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Analyzing with {agent_label} using {memory_label}..."):
            try:
                response = api_request(
                    "POST",
                    "/chat",
                    json={
                        "query": prompt,
                        "conversation_id": st.session_state.conversation_id,
                        "agent_type": selected_agent,
                        "memory_mode": selected_memory,
                    },
                )
                if not response.ok:
                    err_detail = response.json().get("detail", "Error processing request")
                    raise RuntimeError(err_detail)

                data = response.json()
                answer = data.get("answer") or "No answer returned."
                sources = data.get("sources", [])
                st.session_state.conversation_id = data.get("conversation_id") or st.session_state.conversation_id

                profile_name = None
                prompt_lower = prompt.lower()
                patterns = [
                    (r"my name is\s+([A-Za-z0-9_'-]+)", "my name is"),
                    (r"i am\s+([A-Za-z0-9_'-]+)", "i am"),
                    (r"call me\s+([A-Za-z0-9_'-]+)", "call me"),
                    (r"i['’]m\s+([A-Za-z0-9_'-]+)", "i'm"),
                ]
                for pattern, _ in patterns:
                    match = re.search(pattern, prompt, flags=re.IGNORECASE)
                    if match:
                        profile_name = match.group(1)
                        break

                st.session_state.memory_snapshot[selected_memory] = {
                    "mode": selected_memory,
                    "tenant_id": USER_HEADERS.get("X-Tenant-Id"),
                    "user_id": USER_HEADERS.get("X-User-Id"),
                    "turn_count": len(st.session_state.messages) + 1,
                    "last_prompt": prompt,
                    "last_answer": answer,
                    "profile_name": profile_name,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }

                st.markdown(answer)
                if sources:
                    with st.expander(f"🔍 Verified Sources ({len(sources)})", expanded=False):
                        for src in sources:
                            doc_name = src.get("document_name") or src.get("source") or "Enterprise Source"
                            score = src.get("score")
                            score_badge = f" • Score: {int(score * 100)}%" if score is not None else ""
                            st.markdown(
                                f"""
                                <div class="citation-card">
                                    <div class="citation-title">📄 {doc_name}{score_badge}</div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )
            except Exception as exc:
                err_msg = f"Unable to complete response: {exc}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
