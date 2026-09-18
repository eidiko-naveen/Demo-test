"""MnemoRAG Streamlit frontend — chat UI with live memory mode switching."""
import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="MnemoRAG", page_icon="🧠", layout="wide")

if "user_id" not in st.session_state:
    st.session_state.user_id = f"user-{uuid.uuid4().hex[:8]}"
if "session_id" not in st.session_state:
    st.session_state.session_id = f"{st.session_state.user_id}:{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

st.sidebar.title("🧠 MnemoRAG")
st.sidebar.caption(f"Session: `{st.session_state.session_id}`")

try:
    modes = requests.get(f"{BACKEND_URL}/memory-modes", timeout=5).json()["modes"]
except Exception:
    modes = ["buffer", "summary", "entity", "vector", "persistent", "hybrid"]
    st.sidebar.warning("Backend not reachable — using default mode list")

memory_mode = st.sidebar.selectbox("Memory Mode", modes, index=modes.index("hybrid") if "hybrid" in modes else 0)

if st.sidebar.button("🔄 New Session"):
    st.session_state.session_id = f"{st.session_state.user_id}:{uuid.uuid4().hex[:8]}"
    st.session_state.messages = []
    st.rerun()

with st.sidebar.expander("📄 Ingest a document"):
    doc_source = st.text_input("Source name", value="manual-upload")
    doc_text = st.text_area("Text content")
    if st.button("Ingest"):
        resp = requests.post(f"{BACKEND_URL}/ingest", json={"source": doc_source, "text": doc_text}, timeout=60)
        if resp.status_code == 200:
            st.success(f"Stored {resp.json()['chunks_stored']} chunk(s)")
        else:
            st.error(f"Ingest failed ({resp.status_code}): {resp.text}")

st.title("MnemoRAG Chat")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask something..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Thinking ({memory_mode} mode)..."):
            resp = requests.post(
                f"{BACKEND_URL}/chat",
                json={
                    "session_id": st.session_state.session_id,
                    "message": prompt,
                    "memory_mode": memory_mode,
                },
                timeout=60,
            )

            if resp.status_code != 200:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                st.error(f"Chat failed ({resp.status_code}): {detail}")
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"⚠️ Error: {detail}"}
                )
                st.stop()

            data = resp.json()
            st.markdown(data["reply"])

            with st.expander("🔍 Debug: context used"):
                st.markdown(f"**Memory context:**\n```\n{data['memory_context_used']}\n```")
                st.markdown(f"**RAG chunks:**\n```\n{data['rag_chunks_used']}\n```")

    st.session_state.messages.append({"role": "assistant", "content": data["reply"]})