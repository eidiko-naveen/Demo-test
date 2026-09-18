"""
Single entry point for turning a mode name (string, from the API request or
Streamlit dropdown) into a concrete MemoryStrategy instance. This is the
piece that makes "switch memory mode" a runtime choice instead of a
redeploy — routes.py and Streamlit only ever import get_memory_strategy(),
never the individual mode classes.
"""
import structlog

from src.memory.base import MemoryStrategy
from src.memory.buffer import BufferMemory
from src.memory.entity import EntityMemory
from src.memory.hybrid import HybridMemory
from src.memory.persistent import PersistentMemory
from src.memory.summary import SummaryMemory
from src.memory.vector import VectorMemory

logger = structlog.get_logger()

_STRATEGIES: dict[str, type[MemoryStrategy]] = {
    "buffer": BufferMemory,
    "summary": SummaryMemory,
    "entity": EntityMemory,
    "vector": VectorMemory,
    "persistent": PersistentMemory,
    "hybrid": HybridMemory,
}


def get_memory_strategy(mode: str) -> MemoryStrategy:
    """
    Raises ValueError for an unknown mode rather than silently defaulting —
    a typo in the API request should fail loudly, not quietly fall back to
    the wrong memory behavior.
    """
    strategy_cls = _STRATEGIES.get(mode.lower())
    if strategy_cls is None:
        valid = ", ".join(_STRATEGIES.keys())
        raise ValueError(f"Unknown memory mode '{mode}'. Valid modes: {valid}")
    return strategy_cls()


def available_modes() -> list[str]:
    """Used by Streamlit to populate the sidebar dropdown — one source of truth."""
    return list(_STRATEGIES.keys())