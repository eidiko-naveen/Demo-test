from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import tempfile
import logging

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from config.settings import get_settings
from models.llm import get_embed_model
from database.repository import delete_document, record_document
from utils.security import ALLOWED_EXTENSIONS, safe_filename, validate_upload

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_qdrant_client():
    settings = get_settings()
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return QdrantClient(path=settings.qdrant_path)


@lru_cache(maxsize=1)
def get_vector_store():
    settings = get_settings()
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.qdrant_collection,
    )


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _points_for_document(document_id: str, tenant_id: str | None = None) -> list:
    client = get_qdrant_client()
    settings = get_settings()
    points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for point in batch:
            payload = point.payload or {}
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
            document_matches = payload.get("document_id") == document_id or metadata.get("document_id") == document_id
            tenant_matches = tenant_id is None or payload.get("tenant_id") == tenant_id or metadata.get("tenant_id") == tenant_id
            if document_matches and tenant_matches:
                points.append(point)
        if offset is None:
            return points


def _delete_document_vectors(document_id: str, tenant_id: str | None = None) -> int:
    point_ids = [point.id for point in _points_for_document(document_id, tenant_id)]
    if point_ids:
        get_qdrant_client().delete(
            collection_name=get_settings().qdrant_collection,
            points_selector=point_ids,
            wait=True,
        )
    return len(point_ids)


def _count_document_vectors(document_id: str, tenant_id: str | None = None) -> int:
    return len(_points_for_document(document_id, tenant_id))


def _tenant_data_dir(user_id: str, tenant_id: str) -> Path:
    settings = get_settings()
    root = Path(settings.data_dir).resolve()
    # Legacy test settings intentionally exercise a directory directly.
    if (
        getattr(settings, "auth_mode", "development") == "development"
        and getattr(settings, "dev_tenant_id", None) is None
    ):
        return root
    safe_tenant = hashlib.sha256(tenant_id.encode()).hexdigest()[:32]
    destination = (root / "tenants" / safe_tenant).resolve()
    if root not in destination.parents:
        raise ValueError("Invalid tenant data directory")
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _read_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, path)


def _restore_manifest(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.write_text(content, encoding="utf-8")


def _restore_previous_file(path: Path) -> None:
    backup_path = path.parent / f".previous-{path.name}"
    if backup_path.exists():
        if path.exists():
            path.unlink()
        os.replace(backup_path, path)


def ingest_directory(user_id: str = "development-user", tenant_id: str = "development-tenant") -> dict:
    settings = get_settings()
    data_dir = _tenant_data_dir(user_id, tenant_id)
    scoped_tenant = tenant_id if getattr(settings, "dev_tenant_id", None) is not None else None
    paths = [
        path for path in data_dir.iterdir()
        if (
            path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in ALLOWED_EXTENSIONS
        )
    ]
    manifest_path = data_dir / ".ingestion-manifest.json"
    manifest = _read_manifest(manifest_path)
    indexed = skipped = failed = 0
    manifest_changed = False

    for path in paths:
        digest = file_hash(path)
        if manifest.get(path.name) == digest:
            skipped += 1
            continue
        previous_digest = manifest.get(path.name)
        previous_manifest = dict(manifest)
        previous_manifest_content = (
            manifest_path.read_text(encoding="utf-8")
            if manifest_path.exists()
            else None
        )
        document_recorded = False
        vectors_inserted = False
        try:
            loaded = SimpleDirectoryReader(
                input_files=[str(path)], filename_as_id=True
            ).load_data()
            if not loaded:
                raise ValueError("document produced no readable content")
            extracted_chars = sum(
                len(document.get_content())
                if callable(getattr(document, "get_content", None))
                else len(getattr(document, "text", ""))
                for document in loaded
            )
            if extracted_chars > getattr(settings, "max_extracted_chars", 2_000_000):
                raise ValueError("The uploaded document exceeds extraction safety limits.")
            for document in loaded:
                document.metadata.update({
                    "file_name": path.name,
                    "file_hash": digest,
                    "document_id": digest,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "source_id": f"{digest}:{path.name}",
                    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                })
            pipeline = IngestionPipeline(
                transformations=[
                    SentenceSplitter(
                        chunk_size=settings.chunk_size,
                        chunk_overlap=settings.chunk_overlap,
                    ),
                    get_embed_model(),
                ],
                vector_store=get_vector_store(),
            )
            pipeline.run(documents=loaded, num_workers=1)
            if not _count_document_vectors(digest, scoped_tenant):
                raise RuntimeError("index verification returned no document vectors")
            vectors_inserted = True

            if scoped_tenant is not None:
                record_document(digest, path.name, user_id, tenant_id)
                document_recorded = True
            old_digest = manifest.get(path.name)
            manifest[path.name] = digest
            _write_manifest(manifest_path, manifest)
            if old_digest and old_digest != digest:
                if scoped_tenant is None:
                    _delete_document_vectors(old_digest)
                else:
                    _delete_document_vectors(old_digest, scoped_tenant)
        except Exception:
            try:
                if vectors_inserted or _count_document_vectors(digest, scoped_tenant):
                    if scoped_tenant is None:
                        _delete_document_vectors(digest)
                    else:
                        _delete_document_vectors(digest, scoped_tenant)
            except Exception:
                pass
                try:
                    if document_recorded and scoped_tenant is not None:
                        delete_document(digest, tenant_id)
                except Exception:
                    logger.exception("document ownership rollback failed")
            manifest = previous_manifest
            try:
                _restore_manifest(manifest_path, previous_manifest_content)
            except Exception:
                logger.exception("manifest rollback failed")
            _restore_previous_file(path)
            failed += 1
            continue

        backup_path = path.parent / f".previous-{path.name}"
        if backup_path.exists():
            backup_path.unlink()
        manifest_changed = True
        indexed += 1

    current_names = {path.name for path in paths}
    for old_name, old_digest in list(manifest.items()):
        if old_name not in current_names:
            if has_collection():
                if scoped_tenant is None:
                    _delete_document_vectors(old_digest)
                else:
                    _delete_document_vectors(old_digest, scoped_tenant)
            del manifest[old_name]
            manifest_changed = True
    if manifest_changed:
        _write_manifest(manifest_path, manifest)
    get_index.cache_clear()
    return {
        "discovered": len(paths),
        "indexed": indexed,
        "skipped": skipped,
        "failed": failed,
    }


@lru_cache(maxsize=32)
def get_index(user_id: str = "development-user", tenant_id: str = "development-tenant"):
    return VectorStoreIndex.from_vector_store(
        get_vector_store(), embed_model=get_embed_model()
    )


def has_collection() -> bool:
    settings = get_settings()
    try:
        return get_qdrant_client().collection_exists(settings.qdrant_collection)
    except Exception as exc:
        logger.warning("qdrant collection check failed: %s", type(exc).__name__)
        return False


def retrieve_evidence(question: str, top_k: int | None = None, user_id: str = "development-user", tenant_id: str = "development-tenant") -> dict:
    settings = get_settings()
    if not has_collection():
        return {"context": "", "sources": [], "sufficient": False}
    filters = MetadataFilters(filters=[
        MetadataFilter(key="tenant_id", value=tenant_id),
        MetadataFilter(key="user_id", value=user_id),
    ])
    retriever = get_index(user_id, tenant_id).as_retriever(similarity_top_k=top_k or settings.top_k, filters=filters)
    sources = []
    context_parts = []
    for node in retriever.retrieve(question):
        score = round(float(node.score), 3) if node.score is not None else None
        if score is not None and score < settings.relevance_threshold:
            continue
        metadata = node.node.metadata or {}
        if metadata.get("tenant_id") != tenant_id or metadata.get("user_id") != user_id:
            continue
        text = node.node.get_content()[:1000]
        source = {
            "citation_id": f"S{len(sources) + 1}",
            "source_type": "internal",
            "file": metadata.get("file_name", "Unknown"),
            "page": metadata.get("page_label") or metadata.get("page") or "-",
            "score": score,
            "text": text,
            "source_id": metadata.get("source_id", metadata.get("file_name", "unknown")),
            "document_id": metadata.get("document_id"),
        }
        sources.append(source)
        context_parts.append(f"[{source['citation_id']}] {text}")
    return {
        "context": "\n\n".join(context_parts),
        "sources": sources,
        "sufficient": bool(sources),
    }


def query_rag(question: str, top_k: int | None = None, user_id: str = "development-user", tenant_id: str = "development-tenant") -> dict:
    evidence = retrieve_evidence(question, top_k, user_id, tenant_id)
    if not evidence["sufficient"]:
        return {
            "answer": "I couldn't find sufficient information in the connected knowledge base to answer this reliably.",
            "sources": [],
            "context": "",
        }
    return {
        "answer": "",
        "sources": evidence["sources"],
        "context": evidence["context"],
    }


def save_uploaded_file(uploaded_file, user_id: str = "development-user", tenant_id: str = "development-tenant"):
    settings = get_settings()
    content = uploaded_file.getbuffer()
    validate_upload(uploaded_file.name, len(content), settings.upload_max_size_mb, bytes(content), settings)
    name = safe_filename(uploaded_file.name)
    data_dir = _tenant_data_dir(user_id, tenant_id)
    destination = (data_dir / name).resolve()
    if data_dir not in destination.parents:
        raise ValueError("Unsafe upload path")
    digest = hashlib.sha256(content).hexdigest()
    backup_path = data_dir / f".previous-{name}"
    if destination.is_symlink():
        raise ValueError("A file with that name cannot be replaced safely.")
    if destination.exists():
        if file_hash(destination) == digest:
            return name
        os.replace(destination, backup_path)
    fd, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=data_dir)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        if backup_path.exists() and not destination.exists():
            os.replace(backup_path, destination)
        raise
    if getattr(settings, "dev_tenant_id", None) is not None:
        record_document(digest, name, user_id, tenant_id)
    return destination.name
