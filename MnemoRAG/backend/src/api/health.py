"""
Three separate health endpoints, matching the three K8s probe types this
project will eventually use (C13-C15). Kept separate rather than one
generic /health because each probe answers a different question:
  - live: is the process alive at all? (no dependency checks — if this
    fails, K8s kills and restarts the pod)
  - ready: can it actually serve traffic? (checks DB connectivity — if
    this fails, K8s stops routing traffic to it but does NOT restart it)
  - startup: has initial setup (DB tables, extension) completed? (used
    once at boot for slow-starting apps, then K8s stops checking it)
"""
import structlog
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.db.session import AsyncSessionLocal

logger = structlog.get_logger()

router = APIRouter(prefix="/health", tags=["health"])

_startup_complete = False


def mark_startup_complete() -> None:
    """Called once from main.py's lifespan after init_db() succeeds."""
    global _startup_complete
    _startup_complete = True


@router.get("/live")
async def liveness() -> dict:
    """No dependency checks — just confirms the process can respond at all."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness(response: Response) -> dict:
    """Confirms the DB is actually reachable before K8s sends real traffic."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("readiness_check_failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": "database unreachable"}


@router.get("/startup")
async def startup_check(response: Response) -> dict:
    """Confirms init_db() (extension + table creation) has completed."""
    if _startup_complete:
        return {"status": "started"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "starting"}