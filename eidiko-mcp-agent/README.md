# Eidiko AI Enterprise Portal: Official GitHub MCP Assistant

A production-grade **Model Context Protocol (MCP)** application built for **Eidiko Systems Integration**. 

This portal connects an autonomous LLM Agent (**Anthropic Claude Opus / Sonnet**) orchestrated via **LangChain & LangGraph** directly to the **Official GitHub MCP Server (`ghcr.io/github/github-mcp-server`)** over standard stdio process transport.

---

## 🏗️ Architecture & Direct MCP Integration

```text
               USER (Eidiko Web UI / Streamlit)
                              |
                              v
              +-------------------------------+
              |    LangGraph Agent Workflow   |
              |   (Claude Opus / Sonnet)      |
              +---------------+---------------+
                              |
                     [MCP Stdio Aggregator]
                              |
                              v
             +----------------------------------+
             | Official GitHub MCP Server       |
             | (ghcr.io/github/github-mcp-server)|
             | 42+ Official GitHub API Tools    |
             +----------------------------------+
```

### Supported Capabilities (42 Official GitHub Tools)
- **Repositories**: `create_repository`, `search_repositories`, `fork_repository`, `list_repository_collaborators`
- **Code & Files**: `get_file_contents`, `create_or_update_file`, `delete_file`, `push_files`, `search_code`
- **Branches & Commits**: `create_branch`, `list_branches`, `get_commit`, `list_commits`, `search_commits`
- **Issues & PRs**: `list_issues`, `create_issue`, `list_pull_requests`, `create_pull_request`, `merge_pull_request`

---

## 📁 Directory Structure

```text
eidiko-mcp-agent/
├── .env                       # ANTHROPIC_API_KEY, GROQ_API_KEY, GITHUB_TOKEN
├── config.py                  # Models, token, and path configuration
├── requirements.txt           # Production dependency specifications
├── mcp_client/
│   └── sse_aggregator.py      # Direct MCP stdio client aggregator & tool execution engine
├── agent/
│   ├── state.py               # LangGraph AgentState definitions
│   └── graph.py               # LangGraph compiled StateGraph workflow
├── scripts/
│   └── start_ui.py            # Launches Streamlit Web UI
├── ui/
│   ├── app.py                 # Streamlit UI with Eidiko brand identity
│   └── custom_css.py          # Eidiko Dark Glassmorphism CSS theme
└── README.md
```

---

## ⚡ Quickstart Guide

### 1. Set Up Environment & Install Dependencies

```bash
cd "/home/bandaru/Desktop/Kousik/my projects/eidiko-mcp-agent"

# Activate virtual environment
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Update `.env` with your **Anthropic API key** and **GitHub Personal Access Token**:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GITHUB_TOKEN=your_github_personal_access_token_here
LLM_MODEL=claude-opus-4-5
```

### 3. Launch the Official GitHub MCP Dashboard

```bash
PYTHONPATH=. python scripts/start_ui.py
```
This automatically opens your browser to `http://localhost:8501`.

---

## 🎨 Brand Identity

Designed specifically for **Eidiko Systems Integration**:
* **Background**: Deep Midnight Navy (`#0B192C` / `#0F172A`)
* **Primary Accent**: Electric Cyan / Aqua Glow (`#00D2FF` / `#06B6D4`)
* **Design Pattern**: Frosted glassmorphism cards with glowing border highlights.
