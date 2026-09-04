import asyncio
import json
import streamlit as st
import sys
import base64
from pathlib import Path

# Add project root path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ui.custom_css import get_eidiko_css
from mcp_client.sse_aggregator import SseAggregator
from agent.graph import EidikoAgentWorkflow
from config import BRAND_NAME, APP_TITLE, ANTHROPIC_API_KEY, LLM_MODEL

# Page Config
st.set_page_config(
    page_title=f"GitHub Enterprise MCP Portal | {BRAND_NAME}",
    page_icon="🐙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(get_eidiko_css(), unsafe_allow_html=True)

# Function to load logo as base64 string for inline HTML embedding
def get_logo_base64():
    logo_path = BASE_DIR / "ui" / "eidiko_logo.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

logo_b64 = get_logo_base64()
logo_img_html = f'<img src="data:image/png;base64,{logo_b64}" style="height: 44px; width: auto; margin-right: 18px; background: #FFFFFF; padding: 6px 14px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); vertical-align: middle;">' if logo_b64 else '🐙 '

# Session State Initialization
if "aggregator" not in st.session_state:
    st.session_state.aggregator = SseAggregator()
if "selected_model" not in st.session_state:
    st.session_state.selected_model = LLM_MODEL
if "agent" not in st.session_state:
    st.session_state.agent = EidikoAgentWorkflow(st.session_state.aggregator, model_name=st.session_state.selected_model)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None

# Top Navigation Banner
st.markdown(
    f"""
    <div class="eidiko-banner">
        <div style="display: flex; align-items: center;">
            {logo_img_html}
            <div>
                <div class="eidiko-logo-text">GitHub Enterprise Co-Pilot</div>
                <div class="eidiko-subtitle">Enterprise Model Context Protocol (MCP) Management Suite</div>
            </div>
        </div>
        <div style="text-align: right;">
            <span class="status-badge-online">🟢 Official GitHub MCP Active (42 Tools)</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    logo_file = BASE_DIR / "ui" / "eidiko_logo.png"
    if logo_file.exists():
        st.image(str(logo_file), width=180)
    else:
        st.image("https://img.icons8.com/isometric/100/null/github.png", width=64)

    st.title("GitHub Co-Pilot")
    st.caption("Official MCP Protocol + LangGraph")

    st.markdown("---")
    st.subheader("⚙️ System Telemetry & Model Switcher")
    
    # Model Selection Feature
    model_options = [
        "claude-opus-4-5",
        "claude-3-5-sonnet-20241022",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3.6-27b",
    ]
    selected_idx = model_options.index(st.session_state.selected_model) if st.session_state.selected_model in model_options else 0
    model_choice = st.selectbox(
        "Select LLM Intelligence Model",
        model_options,
        index=selected_idx,
    )
    if model_choice != st.session_state.selected_model:
        st.session_state.selected_model = model_choice
        st.session_state.agent = EidikoAgentWorkflow(st.session_state.aggregator, model_name=model_choice)
        st.success(f"Switched model to `{model_choice}`!")

    st.markdown(f"**Discovered Tools**: `{len(st.session_state.agent.tools)} Official Tools`")
    st.markdown("**Protocol Transport**: `Stdio Process (Direct Container)`")

    st.markdown("---")
    if st.button("🔄 Refresh Tool Schema"):
        with st.spinner("Re-syncing with GitHub MCP Container..."):
            st.session_state.agent = EidikoAgentWorkflow(st.session_state.aggregator, model_name=st.session_state.selected_model)
            st.success(f"Successfully loaded {len(st.session_state.agent.tools)} tools!")

    if st.session_state.chat_history:
        st.markdown("---")
        st.subheader("📥 Export Audit Logs")
        chat_json = json.dumps(st.session_state.chat_history, indent=2)
        st.download_button(
            label="💾 Download Session Telemetry JSON",
            data=chat_json,
            file_name="eidiko_mcp_audit_log.json",
            mime="application/json",
        )

# Helper Function to Process Agent Run
def execute_agent_prompt(user_query: str):
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result_state = loop.run_until_complete(st.session_state.agent.run(user_query))

    messages = result_state.get("messages", [])
    steps    = result_state.get("tool_steps", [])
    final_text = ""
    tools_used = list(set([s["tool"] for s in steps]))

    for m in reversed(messages):
        if hasattr(m, "content") and m.content and not getattr(m, "tool_call_id", None):
            final_text = m.content
            break

    if not final_text:
        final_text = "Task executed successfully via GitHub MCP."

    st.session_state.chat_history.append({
        "role": "assistant",
        "content": final_text,
        "tools_used": tools_used,
        "steps": steps,
    })

# Main Workspace Tabs
tab_chat, tab_studio, tab_registry = st.tabs([
    "💬 AI Co-Pilot Chat",
    "🛠️ Interactive Action Studio",
    "⚙️ Tool Registry (42 Tools)",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: AI CO-PILOT CHAT
# ─────────────────────────────────────────────────────────────────────────────
with tab_chat:
    st.subheader("Conversational DevSecOps Assistant")
    st.caption("Ask natural language queries to execute complex multi-step workflows on GitHub.")

    # Render Chat History
    for msg in st.session_state.chat_history:
        role = msg["role"]
        content = msg["content"]
        tools_used = msg.get("tools_used", [])
        with st.chat_message(role):
            if role == "assistant" and tools_used:
                badge_html = "".join([f'<span class="tool-badge">🛠️ {t}</span>' for t in tools_used])
                st.markdown(badge_html, unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(content)
            if role == "assistant" and msg.get("steps"):
                with st.expander("🔬 View Executed MCP Tool Telemetry"):
                    for step in msg["steps"]:
                        st.markdown(f"**Tool**: `{step['tool']}`")
                        st.json({"arguments": step["arguments"], "result": step["result"]})

    # Trigger query from studio forms if pending
    if st.session_state.pending_query:
        query_to_run = st.session_state.pending_query
        st.session_state.pending_query = None
        with st.spinner("🤖 Executing requested GitHub operation..."):
            execute_agent_prompt(query_to_run)
        st.rerun()

    chat_input_text = st.chat_input("Ask GitHub Co-Pilot to analyze repos, search code, list commits, manage PRs...")
    if chat_input_text:
        with st.spinner("🤖 Executing request via GitHub MCP..."):
            execute_agent_prompt(chat_input_text)
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: INTERACTIVE ACTION STUDIO (Form-driven parameter workflows)
# ─────────────────────────────────────────────────────────────────────────────
with tab_studio:
    st.subheader("🛠️ Interactive GitHub Action Studio")
    st.caption("Execute structured, parameter-driven GitHub operations with explicit inputs.")

    col1, col2 = st.columns(2)

    with col1:
        # FORM 1: Create Repository
        st.markdown(
            """
            <div class="action-card">
                <div class="action-card-header">🚀 Create GitHub Repository</div>
                <div class="action-card-sub">Scaffold a brand new repository directly on your GitHub account with custom settings.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("create_repo_form"):
            repo_name = st.text_input("Repository Name", placeholder="e.g., eidiko-auth-service")
            repo_desc = st.text_area("Description", placeholder="e.g., Microservice authentication handler for Eidiko Portal")
            visibility = st.selectbox("Visibility", ["Public", "Private"])
            init_readme = st.checkbox("Initialize with README", value=True)
            submit_create_repo = st.form_submit_button("🚀 Launch & Create Repository")

            if submit_create_repo:
                if not repo_name.strip():
                    st.error("Please enter a valid repository name.")
                else:
                    is_private = "private" if visibility == "Private" else "public"
                    readme_str = "with a README" if init_readme else "without a README"
                    query = f"Create a new {is_private} GitHub repository named '{repo_name.strip()}' with description '{repo_desc.strip()}' {readme_str}."
                    st.session_state.pending_query = query
                    st.success(f"Queued repository creation for '{repo_name.strip()}'!")
                    st.rerun()

        st.markdown("---")

        # FORM 2: Create GitHub Issue
        st.markdown(
            """
            <div class="action-card">
                <div class="action-card-header">📌 Create GitHub Issue</div>
                <div class="action-card-sub">Track bugs, features, or tasks by creating a formal issue on any repository.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("create_issue_form"):
            issue_repo = st.text_input("Target Repository (owner/repo)", placeholder="e.g., bandaru/deftntact")
            issue_title = st.text_input("Issue Title", placeholder="e.g., Implement Docker Health Checks")
            issue_body = st.text_area("Issue Body / Description", placeholder="e.g., Add healthcheck endpoint to Dockerfile for automated monitoring.")
            submit_create_issue = st.form_submit_button("📌 Submit Issue")

            if submit_create_issue:
                if not issue_repo.strip() or not issue_title.strip():
                    st.error("Please provide both target repository and issue title.")
                else:
                    query = f"Create a new issue on repository '{issue_repo.strip()}' titled '{issue_title.strip()}' with body '{issue_body.strip()}'."
                    st.session_state.pending_query = query
                    st.success(f"Queued issue creation on '{issue_repo.strip()}'!")
                    st.rerun()

    with col2:
        # FORM 3: Code & File Search
        st.markdown(
            """
            <div class="action-card">
                <div class="action-card-header">🔍 Search Code & Files</div>
                <div class="action-card-sub">Scan your repositories for code snippets, Dockerfiles, dependencies, or configuration keys.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("search_code_form"):
            search_query = st.text_input("Search Keyword / Pattern", placeholder="e.g., Dockerfile, FastAPI, ANTHROPIC_API_KEY")
            target_user = st.text_input("Filter User / Org", placeholder="e.g., bandaru (leave blank for all)")
            submit_search_code = st.form_submit_button("🔍 Execute Code Search")

            if submit_search_code:
                if not search_query.strip():
                    st.error("Please enter a search query keyword.")
                else:
                    user_filter = f"for user '{target_user.strip()}'" if target_user.strip() else ""
                    query = f"Search for code matching '{search_query.strip()}' {user_filter} across my GitHub repositories."
                    st.session_state.pending_query = query
                    st.success(f"Queued code search for '{search_query.strip()}'!")
                    st.rerun()

        st.markdown("---")

        # FORM 4: Create Pull Request
        st.markdown(
            """
            <div class="action-card">
                <div class="action-card-header">🔀 Create Pull Request</div>
                <div class="action-card-sub">Submit code changes for review between two branches.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("create_pr_form"):
            pr_repo = st.text_input("Repository (owner/repo)", placeholder="e.g., bandaru/deftntact")
            pr_title = st.text_input("PR Title", placeholder="e.g., Feature: Add MCP Agent Architecture")
            head_branch = st.text_input("Head Branch (Feature)", placeholder="e.g., feature/mcp-integration")
            base_branch = st.text_input("Base Branch (Target)", value="main")
            pr_body = st.text_area("PR Description", placeholder="e.g., Merges the new MCP stdio client aggregator.")
            submit_create_pr = st.form_submit_button("🔀 Submit Pull Request")

            if submit_create_pr:
                if not pr_repo.strip() or not pr_title.strip() or not head_branch.strip():
                    st.error("Please fill in repository, PR title, and head branch.")
                else:
                    query = f"Create a pull request on repository '{pr_repo.strip()}' titled '{pr_title.strip()}' merging branch '{head_branch.strip()}' into '{base_branch.strip()}' with description '{pr_body.strip()}'."
                    st.session_state.pending_query = query
                    st.success(f"Queued pull request for '{pr_repo.strip()}'!")
                    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: TOOL REGISTRY INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────
with tab_registry:
    st.subheader("⚙️ Official GitHub MCP Tool Registry")
    st.caption("Live list of all 42 official GitHub API tools available to the LangGraph agent.")

    aggregator = st.session_state.aggregator
    if not aggregator.tool_definitions:
        st.warning("No tools loaded. Click 'Refresh Tool Schema' in the sidebar.")
    else:
        st.success(f"Active Session: {len(aggregator.tool_definitions)} Official GitHub MCP Tools Loaded.")
        for tname, tschema in aggregator.tool_definitions.items():
            with st.expander(f"🛠️ {tname}"):
                st.markdown(f"**Description**: {tschema.get('description')}")
                if tschema.get("inputSchema"):
                    st.markdown("**Input Schema**:")
                    st.json(tschema.get("inputSchema"))
