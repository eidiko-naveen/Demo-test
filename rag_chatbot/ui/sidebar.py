from uuid import uuid4

import streamlit as st
from auth.identity import get_current_identity

from agents.router import AgentMode
from database.repository import (
    create_session,
    delete_session,
    list_sessions,
)
from memory.manager import MemoryMode
from config.settings import get_settings
from rag.engine import (
    ingest_directory,
    save_uploaded_file,
)


def render_sidebar():

    identity = get_current_identity()

    with st.sidebar:

        st.markdown(
            '<div class="brand-mark">EIDI<span>KO</span></div>',
            unsafe_allow_html=True,
        )

        st.caption("Knowledge workspace")

        if st.button(
            "＋ New conversation",
            use_container_width=True,
        ):

            session_id = uuid4().hex

            create_session(session_id, user_id=identity.user_id, tenant_id=identity.tenant_id)

            st.session_state.session_id = (
                session_id
            )

            st.rerun()

        sessions = list_sessions(user_id=identity.user_id, tenant_id=identity.tenant_id)

        if sessions:

            labels = [
                session.title[:40]
                for session in sessions
            ]

            current = next(
                (
                    index
                    for index, session
                    in enumerate(sessions)
                    if session.id
                    == st.session_state.session_id
                ),
                0,
            )

            selected = st.selectbox(
                "Conversation",
                labels,
                index=current,
            )

            selected_session = sessions[
                labels.index(selected)
            ]

            st.caption(
                f"{len(sessions)} saved conversation"
                f"{'s' if len(sessions) != 1 else ''}"
            )

            if (
                selected_session.id
                != st.session_state.session_id
            ):

                st.session_state.session_id = (
                    selected_session.id
                )

                st.rerun()

        st.divider()

        st.markdown("### Workspace controls")

        agent_value = st.selectbox(
            "Agent",
            [
                item.value
                for item in AgentMode
            ],
        )

        memory_value = st.selectbox(
            "Memory",
            [
                item.value
                for item in MemoryMode
            ],
            index=4,
        )

        st.session_state.agent_mode = (
            AgentMode(agent_value)
        )

        st.session_state.memory_mode = (
            MemoryMode(memory_value)
        )

        st.divider()

        st.markdown("### Knowledge base")
        st.caption("Add source files, then index them for grounded answers.")

        files = st.file_uploader(
            "Add documents",
            type=[
                "pdf",
                "txt",
                "md",
                "docx",
                "csv",
                "xlsx",
            ],
            accept_multiple_files=True,
        )

        if files:

            if st.button(
                "Index documents",
                use_container_width=True,
                type="primary",
            ):

                settings = get_settings()
                if len(files) > settings.upload_max_files:
                    st.error(f"You can upload at most {settings.upload_max_files} files at once.")
                    return st.session_state.agent_mode, st.session_state.memory_mode
                if sum(len(uploaded.getbuffer()) for uploaded in files) > settings.upload_max_total_size_mb * 1024 * 1024:
                    st.error("The selected files exceed the total upload limit.")
                    return st.session_state.agent_mode, st.session_state.memory_mode

                for uploaded in files:

                    save_uploaded_file(uploaded, identity.user_id, identity.tenant_id)

                with st.spinner(
                    "Creating embeddings and indexing..."
                ):

                    count = (
                        ingest_directory(identity.user_id, identity.tenant_id)
                    )

                st.success(
                    f"Indexed {count['indexed']} file(s); "
                    f"skipped {count['skipped']}; "
                    f"failed {count['failed']}."
                )

        st.divider()

        if st.button(
            "Delete conversation",
            use_container_width=True,
        ):

            delete_session(st.session_state.session_id, identity.user_id, identity.tenant_id)

            session_id = uuid4().hex

            create_session(session_id, user_id=identity.user_id, tenant_id=identity.tenant_id)

            st.session_state.session_id = (
                session_id
            )

            st.rerun()

        return (
            st.session_state.agent_mode,
            st.session_state.memory_mode,
        )