from types import SimpleNamespace
from unittest.mock import patch
import hashlib

from rag.engine import _delete_document_vectors, ingest_directory


def test_document_vector_cleanup_removes_owned_points_only():
    point_a = SimpleNamespace(id="a", payload={"metadata": {"document_id": "old"}})
    point_b = SimpleNamespace(id="b", payload={"document_id": "other"})

    class Client:
        def __init__(self):
            self.deleted = None

        def scroll(self, **kwargs):
            if kwargs["offset"] is None:
                return [point_a, point_b], "next"
            return [], None

        def delete(self, **kwargs):
            self.deleted = kwargs["points_selector"]

    client = Client()
    settings = SimpleNamespace(qdrant_collection="documents")
    with patch("rag.engine.get_qdrant_client", return_value=client), patch(
        "rag.engine.get_settings", return_value=settings
    ):
        assert _delete_document_vectors("old") == 1
    assert client.deleted == ["a"]


def test_failed_replacement_preserves_old_manifest_and_vectors(tmp_path):
    manifest = tmp_path / ".ingestion-manifest.json"
    manifest.write_text('{"report.txt": "old-hash"}')
    (tmp_path / "report.txt").write_text("new content")
    settings = SimpleNamespace(
        data_dir=str(tmp_path),
        chunk_size=100,
        chunk_overlap=10,
        qdrant_collection="documents",
    )
    with patch("rag.engine.get_settings", return_value=settings), \
         patch("rag.engine.SimpleDirectoryReader") as reader, \
         patch("rag.engine.get_vector_store"), \
         patch("rag.engine.get_embed_model"), \
         patch("rag.engine.has_collection", return_value=True), \
         patch("rag.engine._count_document_vectors", return_value=0), \
         patch("rag.engine._delete_document_vectors") as delete_vectors:
        reader.return_value.load_data.return_value = []
        result = ingest_directory()
    assert result["failed"] == 1
    assert manifest.read_text() == '{"report.txt": "old-hash"}'
    delete_vectors.assert_not_called()


def test_successful_replacement_deletes_old_vectors_after_verification(tmp_path):
    manifest = tmp_path / ".ingestion-manifest.json"
    manifest.write_text('{"report.txt": "old-hash"}')
    (tmp_path / "report.txt").write_text("new content")
    settings = SimpleNamespace(data_dir=str(tmp_path), chunk_size=100, chunk_overlap=10, qdrant_collection="documents")
    with patch("rag.engine.get_settings", return_value=settings), \
         patch("rag.engine.SimpleDirectoryReader") as reader, \
         patch("rag.engine.IngestionPipeline") as pipeline, \
         patch("rag.engine.get_vector_store"), \
         patch("rag.engine.get_embed_model"), \
         patch("rag.engine._count_document_vectors", return_value=1), \
         patch("rag.engine._delete_document_vectors") as delete_vectors, \
         patch("rag.engine.has_collection", return_value=True), \
         patch("rag.engine.get_index"):
        reader.return_value.load_data.return_value = [SimpleNamespace(metadata={})]
        result = ingest_directory()
    assert result["indexed"] == 1
    delete_vectors.assert_called_once_with("old-hash")


def test_post_index_failure_removes_new_vectors_and_restores_old_state(tmp_path):
    manifest = tmp_path / ".ingestion-manifest.json"
    manifest.write_text('{"report.txt": "old-hash"}')
    (tmp_path / ".previous-report.txt").write_text("old content")
    (tmp_path / "report.txt").write_text("new content")
    settings = SimpleNamespace(data_dir=str(tmp_path), chunk_size=100, chunk_overlap=10, qdrant_collection="documents")
    deleted = []

    def delete_vectors(document_id):
        deleted.append(document_id)
        if document_id == "old-hash":
            raise RuntimeError("simulated cleanup failure")
        return 1

    with patch("rag.engine.get_settings", return_value=settings), \
         patch("rag.engine.SimpleDirectoryReader") as reader, \
         patch("rag.engine.IngestionPipeline"), \
         patch("rag.engine.get_vector_store"), \
         patch("rag.engine.get_embed_model"), \
         patch("rag.engine._count_document_vectors", return_value=1), \
         patch("rag.engine._delete_document_vectors", side_effect=delete_vectors), \
         patch("rag.engine.get_index"):
        reader.return_value.load_data.return_value = [SimpleNamespace(metadata={})]
        result = ingest_directory()
    assert result["failed"] == 1
    assert deleted == ["old-hash", hashlib.sha256(b"new content").hexdigest()]
    assert manifest.read_text() == '{"report.txt": "old-hash"}'
    assert (tmp_path / "report.txt").read_text() == "old content"