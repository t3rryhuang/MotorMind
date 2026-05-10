"""
Compact course context for the AI tutor (Gemini prompt material).
"""

from __future__ import annotations

import json
import re
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils.html import strip_tags

from courses.models import Course, TrainingVideo

MAX_TRANSCRIPT_CHARS = 12000
MAX_READING_CHARS = 8000
MAX_CHUNKS = 5
MAX_HISTORY_MESSAGES = 10


def _html_to_plain(text: str, limit: int) -> str:
    raw = strip_tags(text or "")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit] if len(raw) > limit else raw


def build_course_tutor_context(
    course: Course,
    user: AbstractBaseUser | None = None,
) -> dict[str, Any]:
    """
    Return a JSON-serializable dict summarizing course materials for the tutor system prompt.
    """
    out: dict[str, Any] = {
        "course": {
            "title": course.title,
            "description": (course.description or "")[:4000],
        },
        "reading": None,
        "videos": [],
        "reading_source_chunks": [],
        "quizzes": [],
        "quiz_performance": {
            "note": (
                "Per-question right/wrong answers are not stored in the database yet; "
                "only overall quiz scores and pass/fail are available per attempt."
            ),
            "attempts": [],
        },
    }

    try:
        from study_content.models import CourseReadingContext, CourseReadingPage

        page = CourseReadingPage.objects.filter(course=course).first()
        if page and ((page.content_html or "").strip() or (page.title or "").strip()):
            out["reading"] = {
                "title": (page.title or "")[:500],
                "plain_text": _html_to_plain(page.content_html or "", MAX_READING_CHARS),
                "citations": page.citations or [],
            }

        latest_ctx = (
            CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
        )
        if latest_ctx:
            chunks = list(
                latest_ctx.source_chunks.order_by("citation_label", "pk")[:MAX_CHUNKS]
            )
            for c in chunks:
                out["reading_source_chunks"].append(
                    {
                        "citation_label": (c.citation_label or "")[:32],
                        "source_title": (c.source_title or "")[:255],
                        "author": (c.author or "")[:255],
                        "page_number": c.page_number,
                        "chunk_text": (c.chunk_text or "")[:2000],
                    }
                )
    except ImportError:
        pass

    videos = (
        TrainingVideo.objects.filter(course=course)
        .prefetch_related("sections")
        .order_by("created_at")
    )
    for v in videos:
        tr = (v.transcript or "").strip()
        if len(tr) > MAX_TRANSCRIPT_CHARS:
            tr = tr[:MAX_TRANSCRIPT_CHARS] + "\n… [transcript truncated]"
        sections = []
        for s in v.sections.order_by("start_seconds", "order", "pk"):
            sections.append(
                {
                    "title": (s.title or "")[:200],
                    "start_seconds": int(s.start_seconds),
                    "end_seconds": int(s.end_seconds),
                }
            )
        out["videos"].append(
            {
                "title": (v.title or "")[:255],
                "transcript": tr,
                "sections": sections,
            }
        )

    from quizzes.models import Question, Quiz, QuizAttempt

    for quiz in Quiz.objects.filter(course=course).prefetch_related("questions__choices"):
        q_payload: dict[str, Any] = {
            "title": quiz.title,
            "pass_mark": quiz.pass_mark,
            "questions": [],
        }
        for q in quiz.questions.all():
            choices = []
            for ch in q.choices.all():
                choices.append(
                    {
                        "answer_text": (ch.answer_text or "")[:500],
                        "is_correct": ch.is_correct,
                    }
                )
            refs = q.source_refs if isinstance(q.source_refs, list) else []
            q_payload["questions"].append(
                {
                    "question_text": (q.question_text or "")[:2000],
                    "explanation": (q.explanation or "")[:1500],
                    "timestamp_seconds": q.timestamp_seconds,
                    "source_refs": refs[:20],
                    "choices": choices,
                }
            )
        out["quizzes"].append(q_payload)

    if user and user.is_authenticated:
        attempts = (
            QuizAttempt.objects.filter(student=user, quiz__course=course)
            .select_related("quiz")
            .order_by("-created_at")[:8]
        )
        for a in attempts:
            out["quiz_performance"]["attempts"].append(
                {
                    "quiz_title": a.quiz.title,
                    "score": a.score,
                    "passed": a.passed,
                    "created_at": a.created_at.isoformat(),
                }
            )

    return out


def format_context_for_prompt(ctx: dict[str, Any]) -> str:
    """Human-readable block for Gemini."""
    return json.dumps(ctx, indent=2, ensure_ascii=False)


def load_recent_messages_for_llm(
    conversation,
    limit: int = MAX_HISTORY_MESSAGES,
    *,
    exclude_latest_user_turn: bool = False,
):
    """
    Recent messages for the model. If ``exclude_latest_user_turn`` is True, the most
    recent user message (typically just saved for this request) is omitted from the
    history JSON so it is not duplicated with the explicit latest-message line in the prompt.
    """
    from tutor.models import TutorMessage

    qs = conversation.messages.order_by("-created_at")
    if exclude_latest_user_turn:
        latest = qs.first()
        if latest and latest.role == TutorMessage.Role.USER:
            qs = qs.exclude(pk=latest.pk)
    rows = list(qs[:limit])
    rows.reverse()
    out = []
    for m in rows:
        if m.role == TutorMessage.Role.SYSTEM:
            continue
        out.append({"role": m.role, "content": (m.content or "")[:8000]})
    return out
