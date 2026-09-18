from app.rag.types import LoadedDocument, TextChunk


class TextChunker:
    """Split loaded text into bounded overlapping chunks while preserving metadata."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150):
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, documents: list[LoadedDocument]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for document in documents:
            text = " ".join(document.text.split())
            if not text:
                continue
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunks.append(TextChunk(text=text[start:end], metadata=dict(document.metadata)))
                if end == len(text):
                    break
                start = end - self.chunk_overlap
        return chunks
