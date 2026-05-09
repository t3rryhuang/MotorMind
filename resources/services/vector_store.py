"""
ChromaDB persistent client + helpers.

Vectors and full chunk text live here only — not duplicated per-chunk in SQLite.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401
    except ImportError:
        return False
    return True


def get_chroma_client():
    """Return a persistent Chroma client or raise ImportError / RuntimeError with context."""
    if not _chroma_available():
        raise RuntimeError(
            "chromadb is not installed. Run: pip install chromadb"
        )
    import chromadb

    path = Path(settings.VECTOR_DB_PATH)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_collection(name: str | None = None):
    """
    Get or create the resources collection.

    We always pass explicit embeddings on upsert/query_embeddings so the default
    collection embedding function (Chroma default) is not used for writes.
    """
    client = get_chroma_client()
    collection_name = name or getattr(settings, "CHROMA_COLLECTION_NAME", "carhoot_resources")
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be str, int, float, or bool."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            # Store complex types as JSON string for portability / filtering workarounds.
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = str(v)
    return out


def _course_metadata(resource) -> tuple[list[int], list[str], str, str]:
    courses = list(resource.courses.all().order_by("id"))
    ids = [c.id for c in courses if c.id is not None]
    titles = [c.title for c in courses]
    return ids, titles, ",".join(str(i) for i in ids), "|".join(titles)


def add_chunks(resource, chunks: list[dict]) -> list[str]:
    """
    Embed and upsert chunks into Chroma. Each chunk dict must include at least: text, chunk_index, page_number, ...

    Returns list of vector ids stored.
    """
    from resources.services.embeddings import get_embedding_function

    ef = get_embedding_function()
    if ef is None:
        raise RuntimeError("Embedding function unavailable. Install sentence-transformers.")

    collection = get_collection(resource.vector_collection or None)
    course_ids, course_titles, course_ids_csv, course_titles_csv = _course_metadata(resource)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []

    texts = [c["text"] for c in chunks]
    vectors = ef.embed_documents(texts)

    for chunk, emb in zip(chunks, vectors):
        idx = int(chunk.get("chunk_index", 0))
        vid = f"resource_{resource.id}_chunk_{idx}"
        ids.append(vid)
        documents.append(chunk["text"])
        page_number = int(chunk.get("page_number") or 0)
        meta = {
            "resource_id": int(resource.id),
            "resource_title": resource.title or "",
            "resource_type": resource.resource_type or "",
            "isbn": getattr(resource, "isbn", "") or "",
            "source_title": resource.source_title or "",
            "author": resource.author or "",
            "page_number": page_number,
            "section_title": str(chunk.get("section_title") or ""),
            "course_ids_json": json.dumps(course_ids),
            "course_titles_json": json.dumps(course_titles),
            "course_ids_csv": course_ids_csv,
            "course_titles_csv": course_titles_csv,
            "chunk_index": idx,
            "original_filename": resource.original_filename or "",
            "start_seconds": int(chunk.get("start_seconds", -1)),
            "end_seconds": int(chunk.get("end_seconds", -1)),
            "char_start": int(chunk.get("char_start", -1)),
            "char_end": int(chunk.get("char_end", -1)),
        }
        metadatas.append(_sanitize_metadata(meta))
        embeddings.append(emb)

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    logger.info("Chroma upsert: resource_id=%s chunks=%s", resource.id, len(ids))
    return ids


def refresh_resource_chunk_course_metadata(resource, collection_name: str | None = None) -> int:
    """
    Rewrite course_* fields on existing Chroma rows for this resource.

    Used when `Resource.courses` changes so course-scoped search metadata stays
    correct **without** re-extracting, re-chunking, or re-embedding the PDF.
    """
    from resources.models import Resource

    if not isinstance(resource, Resource):
        raise TypeError("resource must be a Resource instance")
    if not _chroma_available():
        logger.warning("Chroma unavailable; skipping course metadata refresh for resource_id=%s", resource.id)
        return 0

    resource = Resource.objects.prefetch_related("courses").get(pk=resource.pk)
    if resource.status != Resource.Status.INGESTED or int(resource.chunk_count or 0) < 1:
        return 0

    course_ids, course_titles, course_ids_csv, course_titles_csv = _course_metadata(resource)
    collection = get_collection(collection_name or resource.vector_collection or None)
    try:
        existing = collection.get(
            where={"resource_id": int(resource.id)},
            include=["metadatas"],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Chroma get for metadata refresh failed: %s", exc)
        return 0

    id_list = existing.get("ids") or []
    old_metas = existing.get("metadatas") or []
    if not id_list:
        return 0

    new_metas: list[dict[str, Any]] = []
    for old in old_metas:
        m = dict(old or {})
        m["course_ids_json"] = json.dumps(course_ids)
        m["course_titles_json"] = json.dumps(course_titles)
        m["course_ids_csv"] = course_ids_csv
        m["course_titles_csv"] = course_titles_csv
        new_metas.append(_sanitize_metadata(m))

    collection.update(ids=id_list, metadatas=new_metas)
    logger.info("Chroma course metadata refresh: resource_id=%s chunks=%s", resource.id, len(id_list))
    return len(id_list)


def delete_resource_vectors(resource_id: int, collection_name: str | None = None) -> int:
    """Delete all vectors whose metadata resource_id matches. Returns number of ids deleted."""
    collection = get_collection(collection_name)
    try:
        existing = collection.get(where={"resource_id": int(resource_id)})
    except Exception as exc:  # pragma: no cover
        logger.warning("Chroma get for delete failed: %s", exc)
        return 0
    id_list = existing.get("ids") or []
    if id_list:
        collection.delete(ids=id_list)
    logger.info("Chroma delete: resource_id=%s removed=%s", resource_id, len(id_list))
    return len(id_list)


def query_similar_chunks(
    query: str,
    top_k: int = 5,
    course_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic search against Chroma. Optional filters applied in Python when needed
    (course membership uses course_ids_csv / JSON list workaround).
    """
    from resources.services.embeddings import get_embedding_function

    ef = get_embedding_function()
    if ef is None:
        raise RuntimeError("Embedding function unavailable.")

    collection = get_collection(collection_name)
    q_emb = [ef.embed_query(query)]
    n_fetch = max(top_k * 8, top_k + 5)

    where: dict[str, Any] | None = None
    if resource_id is not None:
        where = {"resource_id": int(resource_id)}
    if resource_type:
        parts = []
        if resource_id is not None:
            parts.append({"resource_id": int(resource_id)})
        parts.append({"resource_type": str(resource_type)})
        where = {"$and": parts} if len(parts) > 1 else parts[0]

    kwargs: dict[str, Any] = {
        "query_embeddings": q_emb,
        "n_results": n_fetch,
        "include": ["documents", "metadatas", "distances"],
    }
    if where is not None:
        kwargs["where"] = where

    raw = collection.query(**kwargs)
    ids_out = (raw.get("ids") or [[]])[0]
    docs_out = (raw.get("documents") or [[]])[0]
    metas_out = (raw.get("metadatas") or [[]])[0]
    dists_out = (raw.get("distances") or [[]])[0]

    results: list[dict[str, Any]] = []
    for vid, doc, meta, dist in zip(ids_out, docs_out, metas_out, dists_out):
        meta = meta or {}
        rid = int(meta.get("resource_id", 0))
        if resource_type and meta.get("resource_type") != resource_type:
            continue
        if resource_id is not None and rid != int(resource_id):
            continue
        if course_id is not None:
            csv = str(meta.get("course_ids_csv") or "")
            parts = [p.strip() for p in csv.split(",") if p.strip()]
            if str(course_id) not in parts:
                try:
                    cj = meta.get("course_ids_json") or "[]"
                    parsed = json.loads(cj) if isinstance(cj, str) else cj
                    if int(course_id) not in [int(x) for x in parsed]:
                        continue
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        # similarity from cosine distance
        score = None
        if dist is not None:
            try:
                score = max(0.0, min(1.0, 1.0 - float(dist)))
            except (TypeError, ValueError):
                score = None
        results.append(
            {
                "vector_id": vid,
                "text": doc or "",
                "score": score,
                "distance": dist,
                "metadata": meta,
                "resource_id": rid,
            }
        )
        if len(results) >= top_k:
            break
    return results[:top_k]


def clear_collection(collection_name: str | None = None) -> None:
    """Delete and recreate empty collection (management command)."""
    client = get_chroma_client()
    name = collection_name or getattr(settings, "CHROMA_COLLECTION_NAME", "carhoot_resources")
    try:
        client.delete_collection(name)
    except Exception:
        logger.info("Collection %s did not exist or delete failed; continuing.", name)
    get_collection(name)
