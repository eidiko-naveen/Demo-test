from pathlib import Path

from app.rag.loaders.base import DocumentLoader
from app.rag.loaders.builtin import CsvLoader, DocxLoader, JsonLoader, PdfLoader, TextLoader
from app.utils.exceptions import DocumentIngestionError


class LoaderFactory:
    _loaders: dict[str, type[DocumentLoader]] = {
        ".txt": TextLoader,
        ".md": TextLoader,
        ".markdown": TextLoader,
        ".json": JsonLoader,
        ".csv": CsvLoader,
        ".pdf": PdfLoader,
        ".docx": DocxLoader,
    }

    @classmethod
    def create(cls, path: Path) -> DocumentLoader:
        try:
            loader_type = cls._loaders[path.suffix.lower()]
        except KeyError as exc:
            raise DocumentIngestionError(f"Unsupported document type: {path.suffix}") from exc
        return loader_type()
