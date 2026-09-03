# MnemoRAG 🧠

RAG chatbot with 6 pluggable memory modes (Buffer, Summary, Entity, Vector, Persistent, Hybrid), built with FastAPI, Streamlit, Postgres+pgvector, and Claude.

## Architecture
- **backend/** — FastAPI service: RAG retrieval, memory strategies, Claude integration
- **frontend/** — Streamlit chat UI with live memory-mode switching
- **Postgres (pgvector)** — single database backing both RAG documents and all 6 memory modes

## Prerequisites
- Docker Desktop
- `uv` (https://docs.astral.sh/uv/) — only needed for local (non-Docker) dev
- An Anthropic API key

## Quick Start (Docker — recommended)

```bash
# 1. Start Postgres
docker-compose up -d

# 2. Configure secrets
cp backend/.env.example backend/.env
# edit backend/.env and add your ANTHROPIC_API_KEY

# 3. Build images
docker build -t mnemorag-backend ./backend
docker build -t mnemorag-frontend ./frontend

# 4. Network + run
docker network create mnemorag-net
docker network connect mnemorag-net mnemorag-postgres
docker run -d --name backend --network mnemorag-net -p 8000:8000 \
  --env-file backend/.env \
  -e DATABASE_URL=postgresql+asyncpg://mnemorag:mnemorag@mnemorag-postgres:5432/mnemorag \
  mnemorag-backend
docker run -d --name frontend --network mnemorag-net -p 8501:8501 \
  -e BACKEND_URL=http://backend:8000 \
  mnemorag-frontend
```

Open **http://localhost:8501**

## Local Dev (without Docker, for active development)

```bash
# Terminal 1 — Postgres only
docker-compose up -d

# Terminal 2 — backend
cd backend
uv sync
cp .env.example .env   # add your ANTHROPIC_API_KEY
uv run uvicorn src.main:app --reload --port 8000

# Terminal 3 — frontend
cd frontend
uv sync
cp .env.example .env
uv run streamlit run app.py
```

## API
- `POST /chat` — send a message, get a reply (params: `session_id`, `message`, `memory_mode`)
- `POST /ingest` — add a document to the RAG knowledge base
- `GET /memory-modes` — list available memory modes
- `GET /health/live`, `/health/ready`, `/health/startup` — Kubernetes probe endpoints
- Full interactive docs at `http://localhost:8000/docs`

## Memory Modes
| Mode | Behavior |
|---|---|
| `buffer` | Last N raw turns |
| `summary` | LLM-condensed running summary per session |
| `entity` | Structured fact extraction (name/value pairs) per session |
| `vector` | Semantic similarity search over past turns |
| `persistent` | Cross-session recall keyed by user_id |
| `hybrid` | Buffer + Vector combined |

## Deployment
Kubernetes manifests for OCP deployment (Deployments, Services, ConfigMap, Secret, probes, resource limits) live in `k8s/` — see that folder for cluster-specific setup, done in coordination with the DevOps team.