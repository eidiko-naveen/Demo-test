from pathlib import Path
from pathlib import PurePosixPath
import re
import io
import zipfile


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv", ".xlsx"}


def safe_filename(name: str) -> str:
    cleaned = Path(name or "document").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned).strip("._")
    return cleaned or "document"


def validate_upload(name: str, size: int, max_size_mb: int, content: bytes | None = None, settings=None) -> None:
    suffix = Path(name or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("This file type is not supported.")
    if size > max_size_mb * 1024 * 1024:
        raise ValueError(f"Files must be {max_size_mb} MB or smaller.")
    if size == 0:
        raise ValueError("Empty files cannot be indexed.")
    if content is None:
        return
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("The uploaded PDF signature is invalid.")
    if suffix in {".docx", ".xlsx"}:
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("The uploaded Office document is invalid.")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > getattr(settings, "max_archive_members", 2000):
                    raise ValueError("The uploaded archive exceeds safety limits.")
                if any(
                    PurePosixPath(item.filename).is_absolute()
                    or ".." in PurePosixPath(item.filename).parts
                    or (item.external_attr >> 16) & 0o170000 == 0o120000
                    for item in members
                ):
                    raise ValueError("The uploaded archive contains unsafe paths.")
                if sum(item.file_size for item in members) > getattr(settings, "max_archive_uncompressed_mb", 100) * 1024 * 1024:
                    raise ValueError("The uploaded archive exceeds safety limits.")
                required = "word/" if suffix == ".docx" else "xl/"
                if not any(item.filename.startswith(required) for item in members):
                    raise ValueError("The uploaded Office document is invalid.")
        except zipfile.BadZipFile as exc:
            raise ValueError("The uploaded Office document is invalid.") from exc
    elif suffix in {".txt", ".md", ".csv"}:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Text uploads must be valid UTF-8.") from exc