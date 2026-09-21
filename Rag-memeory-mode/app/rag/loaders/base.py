from pathlib import Path
from typing import Protocol

from app.rag.types import LoadedDocument


class DocumentLoader(Protocol):
    def load(self, path: Path) -> list[LoadedDocument]: ...
