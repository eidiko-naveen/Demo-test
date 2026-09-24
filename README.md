# Eidiko AI Enterprise Portal: Groq GPT-OSS + Official GitHub MCP Assistant

A Streamlit GitHub AI assistant built with **LangGraph + Groq + `openai/gpt-oss-120b` + the official GitHub MCP Server**.

## Architecture

```text
User
  │
  ▼
Streamlit UI
  │
  ▼
LangGraph Agent
  │
  ▼
Groq API
openai/gpt-oss-120b
  │
  ▼
MCP stdio client
  │
  ▼
Docker
  │
  ▼
Official GitHub MCP Server
  │
  ▼
GitHub API
```

## What changed

- Claude/Anthropic has been removed from the runtime.
- Primary LLM is Groq `openai/gpt-oss-120b`.
- Optional Groq fallback is `llama-3.1-8b-instant`.
- GitHub MCP remains the tool layer.
- No API keys are included in this repository.

## Requirements

- Python 3.11+ recommended
- Docker installed and available as `docker` in PATH
- A Groq API key
- A GitHub Personal Access Token suitable for the GitHub MCP server

## Run locally

### 1. Extract and enter the project

```bash
unzip MCP-GIthub-Groq-GPT-OSS-120B.zip
cd MCP-GIthub
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=openai/gpt-oss-120b
FALLBACK_LLM_MODEL=llama-3.1-8b-instant
GITHUB_TOKEN=your_github_personal_access_token
```

### 5. Verify Docker

```bash
docker --version
docker ps
```

The MCP client launches the official GitHub MCP container automatically when it discovers or executes tools.

### 6. Start the app

```bash
PYTHONPATH=. python scripts/start_ui.py
```

Or directly:

```bash
streamlit run ui/app.py
```

Open `http://localhost:8501`.

## Test prompts

```text
List my GitHub repositories
```

```text
Search my repositories for MCP projects
```

```text
Show the latest commits from owner/repository
```

```text
Create an issue in owner/repository titled "MCP Agent Test"
```

## Troubleshooting

### Docker not found

If you see `[Errno 2] No such file or directory: 'docker'`, Docker is either not installed or not available in the shell PATH. Run:

```bash
which docker
docker --version
```

### Groq authentication error

Check that `.env` contains a valid `GROQ_API_KEY`, then restart Streamlit. Do not commit `.env`.

### GitHub authentication error

Check `GITHUB_TOKEN` and make sure the token has the permissions required for the GitHub operations you are asking the agent to perform.

## Project structure

```text
MCP-GIthub/
├── agent/
│   ├── graph.py
│   └── state.py
├── mcp_client/
│   └── sse_aggregator.py
├── scripts/
│   └── start_ui.py
├── ui/
│   ├── app.py
│   ├── custom_css.py
│   └── eidiko_logo.png
├── config.py
├── requirements.txt
├── .env.example
└── README.md
```
