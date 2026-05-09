"""
AI-generated multiple-choice question suggestions for the quiz editor.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from courses.models import Course, TrainingVideo

logger = logging.getLogger(__name__)

MIN_READING_CHUNKS_FOR_QUIZ_AI = 5


def get_quiz_ai_gate(course: Course) -> dict[str, Any]:
    """
    UI/API gate: quiz AI needs ≥1 linked training video and ≥5 saved reading chunks
    on the latest CourseReadingContext (from “Find top 5 chunks”).
    """
    video_count = course.videos.count()
    chunk_count = 0
    try:
        from study_content.models import CourseReadingContext

        ctx = CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
        if ctx:
            chunk_count = ctx.source_chunks.count()
    except ImportError:
        chunk_count = 0

    ready = video_count >= 1 and chunk_count >= MIN_READING_CHUNKS_FOR_QUIZ_AI
    parts: list[str] = []
    if video_count < 1:
        parts.append("Link at least one training video to this course.")
    if chunk_count < MIN_READING_CHUNKS_FOR_QUIZ_AI:
        parts.append(
            f'In the course editor, open Reading and run “Find top 5 chunks” so at least '
            f"{MIN_READING_CHUNKS_FOR_QUIZ_AI} chunks are saved for the latest reading context."
        )
    message = " ".join(parts) if parts else ""
    return {
        "ready": ready,
        "video_count": video_count,
        "chunk_count": chunk_count,
        "message": message,
    }


def _transcript_for_quiz(course: Course, video_id: int | None) -> str:
    if video_id:
        v = TrainingVideo.objects.filter(pk=video_id, course_id=course.pk).first()
        if v:
            return (v.transcript or "").strip()
    parts: list[str] = []
    for v in course.videos.order_by("pk"):
        t = (v.transcript or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def _resolve_question_count(mode: str, manual: int | None, transcript_len: int) -> int:
    if mode == "manual" and manual is not None:
        return max(1, min(20, int(manual)))
    # automatic: scale lightly with length, default band 5–10
    base = 5 + min(5, transcript_len // 4000)
    return max(5, min(10, base))


def _load_source_chunks(course: Course):
    """Return saved chunks for the latest reading context only (no auto-retrieval)."""
    try:
        from study_content.models import CourseReadingContext
    except ImportError:
        return []

    ctx = CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
    if ctx and ctx.source_chunks.exists():
        return list(ctx.source_chunks.all())
    return []


def generate_quiz_question_suggestions(
    course: Course,
    *,
    video_id: int | None,
    question_count_mode: str,
    question_count: int | None,
) -> dict[str, Any]:
    """
    Return {"success": bool, "questions": [...], "error": str}.

    Uses transcript + saved reading source chunks on the latest context (≥5 required).
    """
    gate = get_quiz_ai_gate(course)
    if not gate["ready"]:
        return {
            "success": False,
            "questions": [],
            "error": gate["message"] or "Prerequisites for AI quiz suggestions are not met.",
        }

    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "questions": [],
            "error": "AI suggestions are not configured. Set GOOGLE_API_KEY.",
        }

    transcript = _transcript_for_quiz(course, video_id)
    if not transcript.strip():
        return {
            "success": False,
            "questions": [],
            "error": "No video transcript available for this course. Add transcripts first.",
        }

    chunks = _load_source_chunks(course)
    if len(chunks) < MIN_READING_CHUNKS_FOR_QUIZ_AI:
        return {
            "success": False,
            "questions": [],
            "error": (
                f"Need at least {MIN_READING_CHUNKS_FOR_QUIZ_AI} saved reading chunks. "
                'Run “Find top 5 chunks” in the course Reading section, then try again.'
            ),
        }

    chunk_lines = []
    for c in chunks:
        chunk_lines.append(
            f"- [{c.citation_label}] {c.resource_title or c.source_title or 'Reading'} "
            f"(resource_id={c.resource_id or 'n/a'}): {_snippet(c.chunk_text, 900)}"
        )
    chunks_text = "\n".join(chunk_lines)

    n_q = _resolve_question_count(
        question_count_mode or "auto",
        question_count,
        len(transcript),
    )

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()
    tr_snip = transcript[:14000]

    prompt = (
        "You write assessment items for an automotive electronics / diagnostics course. "
        f"Generate exactly {n_q} multiple-choice questions. "
        "Each question must test understanding and diagnostic reasoning, not trivia. "
        "Use ONLY the transcript excerpt and reading excerpts below. Do not invent facts. "
        "Prefer 4 answer options per question with exactly one correct answer. "
        "Include a concise explanation per question. "
        "Add source_refs as a list of citation ids like [\"V1\",\"B2\"] referencing transcript [V1] or book chunk labels [B1]..[B5]. "
        "Return STRICT JSON: {\"questions\":[{\"question_text\":...,\"explanation\":...,\"timestamp_seconds\":null,"
        "\"answers\":[{\"answer_text\":...,\"is_correct\":true/false},...],\"source_refs\":[\"V1\",\"B2\"]}]}\n\n"
        f"Transcript excerpt (cite as [V1]):\n{tr_snip}\n\nReading excerpts:\n{chunks_text}\n"
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
        except Exception:
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
        logger.exception("Quiz AI suggestions failed")
        return {"success": False, "questions": [], "error": f"AI request failed: {exc}"}

    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list):
        return {"success": False, "questions": [], "error": "Invalid AI response shape."}

    cleaned: list[dict[str, Any]] = []
    for q in questions[:20]:
        if not isinstance(q, dict):
            continue
        qtext = (q.get("question_text") or "").strip()
        if not qtext:
            continue
        answers_in = q.get("answers") if isinstance(q.get("answers"), list) else []
        answers_out = []
        for a in answers_in[:6]:
            if not isinstance(a, dict):
                continue
            at = (a.get("answer_text") or "").strip()
            if not at:
                continue
            answers_out.append(
                {
                    "answer_text": at[:500],
                    "is_correct": bool(a.get("is_correct")),
                }
            )
        if len(answers_out) < 2:
            continue
        refs = q.get("source_refs")
        if not isinstance(refs, list):
            refs = []
        refs = [str(x).strip() for x in refs if str(x).strip()][:8]
        cleaned.append(
            {
                "question_text": qtext,
                "explanation": (q.get("explanation") or "").strip(),
                "timestamp_seconds": q.get("timestamp_seconds"),
                "answers": answers_out,
                "source_refs": refs,
            }
        )

    if not cleaned:
        return {
            "success": False,
            "questions": [],
            "error": "The model did not return usable questions.",
        }

    return {"success": True, "questions": cleaned, "error": ""}


def _snippet(text: str, limit: int) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:limit] if len(t) > limit else t
