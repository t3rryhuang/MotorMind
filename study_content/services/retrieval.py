"""
Select top-k Chroma chunks globally across all resources linked to a course.
"""

from __future__ import annotations

import logging


from courses.models import Course, TrainingVideo
from resources.models import Resource
from resources.services.vector_store import query_similar_chunks
from study_content.models import CourseReadingContext, CourseReadingSourceChunk

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """User-facing retrieval failure (empty transcript, no resources, etc.)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _transcript_for_query(course: Course, video: TrainingVideo | None) -> str:
    if video is not None:
        return (video.transcript or "").strip()
    parts: list[str] = []
    for v in course.videos.order_by("pk"):
        t = (v.transcript or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def select_top_chunks_for_course_reading(
    course: Course,
    video: TrainingVideo | None = None,
    top_k: int = 5,
    user=None,
) -> CourseReadingContext:
    """
    Embed transcript query, search Chroma, keep global top_k hits for this course.

    Persists `CourseReadingContext` and `CourseReadingSourceChunk` rows.
    """
    text = _transcript_for_query(course, video)
    if not text:
        raise RetrievalError(
            "No video transcript is available for this course. "
            "Add transcripts to training videos (or use Auto-fill on each video) first."
        )

    resource_ids = set(course.resources.values_list("pk", flat=True))
    if not resource_ids:
        raise RetrievalError(
            "No books or resources are linked to this course. "
            "Attach resources from the course editor before finding reading chunks."
        )

    max_vec = 400
    hits: list[dict] = []
    for _ in range(5):
        hits = query_similar_chunks(
            text,
            top_k=top_k,
            course_id=course.pk,
            max_vector_results=max_vec,
        )
        if len(hits) >= top_k or max_vec >= 2400:
            break
        max_vec = min(max_vec * 2, 2400)

    hits = hits[:top_k]

    ctx = CourseReadingContext.objects.create(
        course=course,
        video=video,
        query_text=text[:500000],
        top_k=top_k,
        created_by=user if getattr(user, "pk", None) else None,
    )

    for i, h in enumerate(hits, start=1):
        meta = h.get("metadata") or {}
        rid = int(h.get("resource_id") or meta.get("resource_id") or 0)
        resource = Resource.objects.filter(pk=rid).first() if rid else None
        chunk_idx = meta.get("chunk_index")
        try:
            chunk_index = int(chunk_idx) if chunk_idx not in (None, "") else None
        except (TypeError, ValueError):
            chunk_index = None
        pn = meta.get("page_number")
        try:
            page_number = int(pn) if pn not in (None, "") else None
        except (TypeError, ValueError):
            page_number = None

        CourseReadingSourceChunk.objects.create(
            context=ctx,
            course=course,
            video=video,
            resource=resource,
            vector_id=str(h.get("vector_id") or "")[:256],
            chunk_text=(h.get("text") or "")[:50000],
            score=h.get("score"),
            chunk_index=chunk_index,
            page_number=page_number,
            source_title=str(meta.get("source_title") or "")[:255],
            author=str(meta.get("author") or "")[:255],
            resource_title=str(meta.get("resource_title") or "")[:255],
            citation_label=f"B{i}",
            metadata=dict(meta) if isinstance(meta, dict) else {},
        )

    if not hits:
        logger.warning(
            "Course reading retrieval returned 0 chunks (course_id=%s). "
            "Vectors may be missing course metadata — try re-linking resources or re-ingest.",
            course.pk,
        )

    return ctx
