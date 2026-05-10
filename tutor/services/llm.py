"""
Gemini-backed tutor replies.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser

from courses.models import Course

from .context import (
    build_course_tutor_context,
    format_context_for_prompt,
    load_recent_messages_for_llm,
)

logger = logging.getLogger(__name__)


SYSTEM_INSTRUCTIONS_BASE = """You are a friendly automotive electronics tutor on Car-Hoot — like an experienced trainer in a workshop, not a textbook.
Sound natural and conversational. Use the course context as your source of truth.
Mention video moments casually when helpful (e.g. “around 1:30 in the video…”).
Mention book chunks with short citation tags like [B2] only when it really helps — no long citation dumps.
Do not invent facts, tools, or procedures not supported by the context. If something is missing from the materials, say so briefly.
Do not give away quiz answers unless the student has already tried the quiz or clearly wants an explanation of why an answer is right.
Avoid stiff phrases like “According to the transcript…” — just explain plainly.
"""

SYSTEM_INSTRUCTIONS_TYPED = """Default reply length: about 1–3 short paragraphs, usually under ~150 words unless the question needs more.
Optionally end with one short follow-up question if it helps the student."""

SYSTEM_INSTRUCTIONS_SPOKEN = """VOICE / SPOKEN MODE (strict):
- Maximum about 100 words total.
- Short sentences. No bullet walls. No essay tone.
- At most ONE short follow-up question at the end.
- This will be read aloud — write the way you would speak."""


def generate_tutor_reply(
    course: Course,
    user: AbstractBaseUser,
    conversation,
    user_message: str,
    *,
    spoken_mode: bool = False,
) -> dict[str, Any]:
    """
    Return {"success": bool, "reply": str, "error": str, "warnings": list[str]}.
    """
    warnings: list[str] = []
    api_key = (getattr(settings, "GOOGLE_API_KEY", None) or "").strip()
    if not api_key:
        return {
            "success": False,
            "reply": "",
            "error": "AI tutor is not configured. Set GOOGLE_API_KEY.",
            "warnings": warnings,
        }

    model_name = (getattr(settings, "GOOGLE_MODEL_NAME", None) or "gemma-3-27b-it").strip()
    ctx = build_course_tutor_context(course, user)
    ctx_block = format_context_for_prompt(ctx)
    history = load_recent_messages_for_llm(
        conversation, exclude_latest_user_turn=True
    )

    style = SYSTEM_INSTRUCTIONS_BASE
    if spoken_mode:
        style += "\n" + SYSTEM_INSTRUCTIONS_SPOKEN
    else:
        style += "\n" + SYSTEM_INSTRUCTIONS_TYPED

    parts = [
        style,
        "\n--- COURSE CONTEXT (JSON) ---\n",
        ctx_block,
        "\n--- RECENT CHAT (most recent last) ---\n",
        json.dumps(history, ensure_ascii=False),
        "\nThe student's latest message is below. Respond helpfully.\n",
        (user_message or "").strip()[:8000],
    ]
    prompt = "\n".join(parts)

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text and getattr(response, "candidates", None):
            chunks = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        chunks.append(p.text)
            text = "\n".join(chunks).strip()
        if not text:
            return {
                "success": False,
                "reply": "",
                "error": "The model returned an empty response. Try again later.",
                "warnings": warnings,
            }
        return {"success": True, "reply": text, "error": "", "warnings": warnings}
    except Exception as exc:
        logger.exception("Tutor Gemini call failed")
        return {
            "success": False,
            "reply": "",
            "error": f"AI tutor request failed: {exc}",
            "warnings": warnings,
        }
