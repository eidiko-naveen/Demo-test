"""
FastAPI application entrypoint. Wires together the lifespan (startup DB
init + graceful shutdown), routers, CORS (for the Streamlit frontend), and
structured logging. This is what `uvicorn src.main:app` actually runs.
"""
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import mark_startup_complete
from src.api.health import router as health_router
from src.api.routes import router as chat_router
from src.config import get_settings
from src.db.session import close_db, init_db

settings = get_settings()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(settings.log_level)),
    processors=[
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: initialize DB (extension + tables), mark startup probe green.
    Shutdown: close DB connection pool on SIGTERM — satisfies graceful
    shutdown (C22). FastAPI/uvicorn translates SIGTERM into this lifespan's
    exit path automatically, no manual signal handler needed.
    """
    logger.info("app_starting")
    await init_db()
    mark_startup_complete()
    logger.info("app_ready")

    yield

    logger.info("app_shutting_down")
    await close_db()
    logger.info("app_shutdown_complete")


app = FastAPI(
    title="MnemoRAG",
    description="RAG chatbot with 6 pluggable memory modes",
    version="0.1.0",
    lifespan=lifespan,
)

# Streamlit runs on a different port/origin locally, and on a different
# Service in K8s later — CORS must allow it explicitly rather than "*"
# in anything resembling production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the frontend's actual origin before real production use
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)