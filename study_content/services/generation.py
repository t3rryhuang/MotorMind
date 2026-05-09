"""
AI generation for course Reading pages (Gemini / Google AI).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from courses.models import Course, TrainingVideo
from study_content.citation_format import (
    citations_json_from_chunks,
    replace_label_citations_in_html,
    video_transcript_hover_title,
)
from study_content.models import CourseReadingContext, CourseReadingPage

logger = logging.getLogger(__name__)


def _snippet(text: str, limit: int = 3500) -> str:
    t = (text or "").strip()
    return t[:limit] if len(t) > limit else t


def generate_course_reading(
    course: Course,
    context: CourseReadingContext,
    user=None,
) -> CourseReadingPage:
    """
    Build / update `CourseReadingPage` from course metadata, transcript, and saved chunks.

    Expects `context.source_chunks` to be populated (run retrieval first).
    """
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "Reading generation is not configured. Set GOOGLE_API_KEY."
        )

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()

    chunks = list(context.source_chunks.select_related("resource", "video").all())
    if not chunks:
        raise ValueError(
            "No saved source chunks for this context. Run “Find top 5 chunks” first."
        )

    video = context.video
    if video:
        v_title = video.title
        transcript = _snippet(video.transcript or "")
    else:
        v_title = "Course videos (combined)"
        transcript = _snippet(context.query_text)

    chunk_blocks = []
    for c in chunks:
        rt = c.resource_title or c.source_title or ""
        chunk_blocks.append(
            f"- [{c.citation_label}] resource_id={c.resource_id or 'n/a'} "
            f"title={rt!r} author={c.author!r} page={c.page_number} "
            f"vector_id={c.vector_id!r}\n  excerpt: {_snippet(c.chunk_text, 1200)!r}"
        )
    chunks_text = "\n".join(chunk_blocks)

    prompt = (
        "You are an automotive / technical education author writing a BBC Bitesize-style reading. "
        "Use ONLY the transcript excerpt and numbered book excerpts below. "
        "Do not copy long passages; paraphrase in your own words. "
        "Cite book claims using ONLY the bracket labels [B1], [B2], … exactly as listed below (one per excerpt). "
        "Cite the transcript using [V1]. These placeholders will be turned into author surnames with hover details for students. "
        "Include: a short introduction, main sections, a “Key takeaways” section, and a “Common mistakes” section. "
        "Include at least one simple Mermaid diagram when it helps (e.g. flowchart LR). "
        "In content_html, place each diagram using "
        '<div data-diagram-id=\"DIAGRAM_ID\" class=\"reading-diagram float-end\"></div> '
        "where DIAGRAM_ID matches an entry in the diagrams array. "
        "Return STRICT JSON only with this shape:\n"
        '{"title": string, "summary": string, "content_html": string, '
        '"citations": ['
        '{"id": string, "type": "book"|"video", "source_title": string, "author": string, '
        '"page_number": number|null, "vector_id": string, "resource_id": number|null, '
        '"video_title": string|null, "timestamp": null}], '
        '"diagrams": ['
        '{"id": string, "title": string, "type": "mermaid", "code": string, "caption": string}'
        "]}\n\n"
        f"Course title: {course.title}\n"
        f"Course description: {_snippet(course.description or '', 800)}\n\n"
        f"Video context title: {v_title}\n"
        f"Transcript excerpt for [V1] citations:\n{transcript}\n\n"
        f"Book/resource excerpts (use only these ids for book citations):\n{chunks_text}\n"
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        try:
            from google.generativeai.types import GenerationConfig

            response = model.generate_content(
                prompt,
                generation_config=GenerationConfig(response_mime_type="application/json"),
            )
        except (ImportError, TypeError, ValueError):
            response = model.generate_content(prompt)
        raw_text = (getattr(response, "text", None) or "").strip()
        if not raw_text and getattr(response, "candidates", None):
            parts = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            raw_text = "\n".join(parts).strip()
        data = json.loads(raw_text)
    except Exception as exc:
        logger.exception("Reading generation failed")
        raise ValueError(f"AI reading generation failed: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Model returned invalid JSON root.")

    title = (data.get("title") or f"{course.title} reading")[:255]
    content_html = (data.get("content_html") or "").strip()
    diagrams = data.get("diagrams") if isinstance(data.get("diagrams"), list) else []

    video_hover = video_transcript_hover_title(v_title)
    content_html = replace_label_citations_in_html(
        content_html, chunks, video_hover=video_hover
    )
    citations = citations_json_from_chunks(chunks, video_title=v_title)

    page, _created = CourseReadingPage.objects.get_or_create(course=course)
    page.context = context
    page.title = title
    page.content_html = content_html
    page.citations = citations
    page.diagrams = diagrams
    page.editor_json = {
        "summary": data.get("summary") or "",
        "generated": True,
    }
    page.generated_by_model = model_name
    page.generated_from = {
        "context_id": context.pk,
        "chunk_ids": [c.pk for c in chunks],
        "video_id": video.pk if video else None,
    }
    page.is_teacher_edited = False
    page.save()
    return page
