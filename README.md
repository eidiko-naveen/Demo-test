<<<<<<< HEAD
# Enterprise RAG Platform

Modular monolith foundation for an enterprise retrieval-augmented generation platform with FastAPI, LangGraph, Qdrant, PostgreSQL, Groq, and Streamlit.

## Phase 1

This initial phase provides:

- Centralized Pydantic Settings configuration
- FastAPI application factory and versioned health endpoints
- Async SQLAlchemy models and tenant-aware repositories
- Alembic migration scaffolding for PostgreSQL
- Document loaders, chunking, embeddings, and Qdrant ingestion pipeline
- Shared LangGraph state, routing, and execution workflow
- Groq LLM abstraction and citation-aware RAG agent
- Configurable memory managers for all requested memory modes
- Provider-neutral external research tools and Research Agent
- Hybrid Agent with selective enterprise/research routing
- Versioned FastAPI contracts and service boundaries
- Development authentication and tenant-scoped conversation services
- Lazy PostgreSQL session wiring for conversation APIs
- Docker Compose services for the application, PostgreSQL, and Qdrant
- Streamlit UI shell with agent and memory selectors
- Test and packaging configuration

The local environment currently provides Python 3.10.12. The project targets Python 3.12+ as declared in `pyproject.toml`; use a Python 3.12 virtual environment before installing the full dependency set.

## Run locally

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,rag,dev]"
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000/api/v1/health`. Start the UI separately with:

```bash
streamlit run ui/streamlit_app.py
```

## Run with Docker

```bash
cp .env.example .env
docker compose up -d --build
```

After creating the first migration revision, apply database changes with:

```bash
alembic upgrade head
```

The application does not create tables during startup. Database schema changes are managed through Alembic migrations.

The ingestion pipeline accepts PDF, DOCX, TXT, Markdown, CSV, and JSON files. It adds tenant, user, checksum, version, source, and chunk metadata to every Qdrant payload. The pipeline can be used from a service or script with `IngestionPipeline.ingest(...)`.

The graph builder in `app/graph/builder.py` provides explicit RAG, research, and hybrid execution paths. Provider execution and memory persistence are intentionally separate node boundaries for the next phases.

The RAG agent uses `LLMProvider`, `EnterpriseRetriever`, and structured `AgentResponse` contracts. Groq is loaded only when configured, and retrieved documents are passed as untrusted, labeled context.

`MemoryFactory` supports no memory, buffer, window, summary, summary buffer, entity, long-term, semantic, and persistent conversation modes. Stores are injected into the managers, keeping memory behavior independent from PostgreSQL and ready for service-layer repository adapters.

External research uses `SearchProvider`, `WebSearchTool`, `ResearchService`, and `ResearchAgent` contracts. Search providers can be replaced without changing the agent, and tool output is labeled as untrusted research context.

`HybridAgent` routes enterprise questions to retrieval, current or industry questions to research, and comparison questions to both. Combined answers keep enterprise knowledge and external research in separate labeled prompt sections and degrade to enterprise evidence when research is unavailable.

The API foundation is available under `/api/v1` with agent metadata, memory modes, chat, conversation, and document upload routes. Chat and persistence dependencies are injected through application state so importing the API does not create provider or database clients.

Development authentication uses `AUTH_MODE=mock` with optional `X-User-Id` and `X-Tenant-Id` headers. The security boundary is isolated in `app/security/auth.py`, allowing JWT/OAuth resolution to replace it without changing services. `ConversationService` forwards tenant and user scope to repositories for every operation.

Conversation list, create, get, and archive routes use FastAPI dependency injection with lazy SQLAlchemy sessions. Importing the application does not require a live PostgreSQL connection; database access begins when a persistence endpoint is invoked.

Future phases add persistence, ingestion, retrieval, LangGraph orchestration, agents, memory implementations, API resources, and enterprise monitoring incrementally.
=======
# Demo-test
>>>>>>> 05914fdbc974380648171701ee90a3792ffac575
