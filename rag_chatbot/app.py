from uuid import uuid4
import logging

import streamlit as st

from services.health import validate_startup
from utils.logging import configure_logging
from agents.router import run_agent
from auth.identity import get_current_identity
from config.settings import get_settings
from database.repository import (
    add_message,
    create_session,
    get_messages,
)
from memory.manager import MemoryManager
from models.llm import get_langfuse
from rag.engine import has_collection
from ui.sidebar import render_sidebar
from ui.styles import apply_styles
from utils.export import transcript_markdown


logger = logging.getLogger(__name__)

configure_logging()
try:
    validate_startup()
except ValueError as exc:
    logger.error("startup validation failed: %s", str(exc))
    st.error(f"Application configuration is invalid: {exc}")
    st.stop()
identity = get_current_identity()


st.set_page_config(
    page_title="Enterprise RAG",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


apply_styles()


if "session_id" not in st.session_state:

    session_id = uuid4().hex

    create_session(session_id, user_id=identity.user_id, tenant_id=identity.tenant_id)

    st.session_state.session_id = (
        session_id
    )


agent_mode, memory_mode = (
    render_sidebar()
)


st.markdown(
    """
<div class="hero">
<div class="eyebrow">EIDIKO knowledge intelligence</div>
<h1>Ask your knowledge base with confidence.</h1>
<p>Grounded answers from your documents, shaped by the agent and memory mode you choose.</p>

</div>
""",
    unsafe_allow_html=True,
)


messages = get_messages(
    st.session_state.session_id,
    user_id=identity.user_id,
    tenant_id=identity.tenant_id,
)


if not messages:

    knowledge_status = (
            "Connected"
        if has_collection()
        else "Ready for documents"
    )

    st.markdown(
        f"""
<div class="welcome-panel">
<div class="eyebrow">{knowledge_status}</div>
<h2>What would you like to find?</h2>
<p>Start a focused conversation about policies, reports, project files, or any other material in your workspace.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Agent", agent_mode.value)
    metric_two.metric("Memory", memory_mode.value)
    metric_three.metric(
        "Indexed",
        "Available" if has_collection() else "None yet",
    )


for message in messages:

    role = (
        "user"
        if message.role == "user"
        else "assistant"
    )

    with st.chat_message(role):

        st.markdown(
            message.content
        )


prompt = st.chat_input(
    "Ask something about your knowledge base..."
)


if prompt:

    add_message(
        st.session_state.session_id,
        "user",
        prompt,
        identity.user_id,
        identity.tenant_id,
    )

    with st.chat_message("user"):

        st.markdown(prompt)

    memory = MemoryManager(
        st.session_state.session_id,
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
    )

    context = memory.context(
        memory_mode
    )

    with st.chat_message("assistant"):

        with st.spinner(
            "Thinking..."
        ):

            try:

                langfuse = get_langfuse()

                if langfuse is None:

                    result = run_agent(
                        agent=agent_mode,
                        question=prompt,
                        memory_context=context,
                        user_id=identity.user_id,
                        tenant_id=identity.tenant_id,
                    )

                else:

                    with langfuse.start_as_current_observation(
                        name="chat-request",
                        as_type="chain",
                        input={
                            "question": prompt if get_settings().langfuse_capture_content else "[redacted]",
                            "agent": agent_mode.value,
                            "memory_mode": memory_mode.value,
                        },
                        metadata={
                            "session_id": "[redacted]",
                        },
                    ) as trace:

                        result = run_agent(
                            agent=agent_mode,
                            question=prompt,
                            memory_context=context,
                            user_id=identity.user_id,
                            tenant_id=identity.tenant_id,
                        )

                        trace.update(
                            output={
                                "answer": result.answer if get_settings().langfuse_capture_content else "[redacted]",
                                "source_count": len(result.sources),
                            },
                        )

                st.markdown(
                    result.answer
                )

                st.caption(
                    f"🤖 {result.agent}  ·  "
                    f"🧠 {memory_mode.value}  ·  "
                    f"📚 {len(result.sources)} sources"
                )

                if result.sources:

                    with st.expander(
                        "🔎 Sources"
                    ):

                        for index, source in enumerate(
                            result.sources,
                            1,
                        ):

                            score = (
                                ""
                                if source["score"]
                                is None
                                else
                                f" · score "
                                f"{source['score']}"
                            )

                            source_text = source["text"].replace(
                                "\n",
                                " ",
                            )

                            st.write(
                                f"{index}. {source['file']} "
                                f"· page {source['page']}{score}"
                            )
                            st.caption(source_text)

                memory.save_assistant(
                    result.answer
                )

                memory.refresh_summary()

            except Exception as exc:

                logger.exception("chat request failed: %s", type(exc).__name__)

                st.error(
                    "Unable to process the request right now. "
                    "Please try again or check your connection."
                )

            finally:

                langfuse = get_langfuse()

                if langfuse is not None:

                    langfuse.flush()


current_messages = get_messages(
    st.session_state.session_id,
    user_id=identity.user_id,
    tenant_id=identity.tenant_id,
)


if current_messages:

    st.divider()

    export_data = transcript_markdown(
        [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in current_messages
        ]
    )

    st.download_button(
        "Export conversation",
        export_data,
        file_name="conversation.md",
        mime="text/markdown",
    )