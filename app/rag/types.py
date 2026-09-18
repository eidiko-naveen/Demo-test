from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LoadedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TextChunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
