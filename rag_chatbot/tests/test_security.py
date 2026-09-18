from pathlib import Path
import io
import zipfile
from unittest.mock import patch

import pytest

from utils.security import safe_filename, validate_upload
from rag.engine import save_uploaded_file


def test_safe_filename_removes_path_and_shell_characters():
    assert safe_filename("../../report;rm -rf.txt") == "report_rm_-rf.txt"


def test_upload_validation_rejects_large_and_unknown_files():
    with pytest.raises(ValueError):
        validate_upload("report.exe", 10, 25)
    with pytest.raises(ValueError):
        validate_upload("report.pdf", 26 * 1024 * 1024, 25)


def test_upload_collision_replaces_logical_filename(tmp_path):
    existing = tmp_path / "report.txt"
    existing.write_bytes(b"old")
    settings = type("Settings", (), {"data_dir": str(tmp_path), "upload_max_size_mb": 1})()
    uploaded = type("Upload", (), {"name": "report.txt", "getbuffer": lambda self: b"new"})()
    with patch("rag.engine.get_settings", return_value=settings):
        saved = save_uploaded_file(uploaded)
    assert saved == "report.txt"
    assert existing.read_bytes() == b"new"
    assert (tmp_path / ".previous-report.txt").read_bytes() == b"old"


def test_archive_validation_rejects_traversal_member():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as compressed:
        compressed.writestr("../../outside.txt", "unsafe")
    settings = type("Settings", (), {"max_archive_members": 10, "max_archive_uncompressed_mb": 1})()
    with pytest.raises(ValueError, match="unsafe paths"):
        validate_upload("file.docx", len(archive.getvalue()), 1, archive.getvalue(), settings)


def test_failed_upload_replacement_restores_previous_file(tmp_path):
    existing = tmp_path / "report.txt"
    existing.write_bytes(b"old")
    settings = type("Settings", (), {"data_dir": str(tmp_path), "upload_max_size_mb": 1})()
    uploaded = type("Upload", (), {"name": "report.txt", "getbuffer": lambda self: b"new"})()
    with patch("rag.engine.get_settings", return_value=settings), patch("rag.engine.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            save_uploaded_file(uploaded)
    assert existing.read_bytes() == b"old"