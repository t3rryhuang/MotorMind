"""
Generate a short course-style description using Google Generative AI (optional).

Requires GOOGLE_API_KEY. Model name from GOOGLE_MODEL_NAME (default: gemma-3-27b-it).
"""

from __future__ import annotations

import os
from typing import Any


def generate_video_description(
    title: str,
    youtube_description: str = "",
    transcript: str = "",
) -> dict[str, Any]:
    """
    Return {"success": bool, "description": str, "error": str}.

    If GOOGLE_API_KEY is missing, returns a clear not-configured message.
    """
    title = (title or "").strip()
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "description": "",
            "error": "AI description generation is not configured. Set GOOGLE_API_KEY.",
        }

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()

    yt_desc = (youtube_description or "").strip()
    tr = (transcript or "").strip()
    # Keep prompt size reasonable
    tr_snip = tr[:12000] if len(tr) > 12000 else tr
    yt_snip = yt_desc[:4000] if len(yt_desc) > 4000 else yt_desc

    prompt = (
        "You are writing a short description for an automotive electronics education course video. "
        "Write 2-3 clear sentences in a professional teaching tone. "
        "Base your answer ONLY on the title, optional YouTube description, and optional transcript below. "
        "Do not invent facts, part numbers, or claims not supported by the text.\n\n"
        f"Title:\n{title or '(none)'}\n\n"
        f"YouTube description (may be empty):\n{yt_snip or '(none)'}\n\n"
        f"Transcript excerpt (may be empty):\n{tr_snip or '(none)'}\n"
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text and getattr(response, "candidates", None):
            # Some responses use candidates/parts
            parts = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            text = "\n".join(parts).strip()
        if not text:
            return {
                "success": False,
                "description": "",
                "error": "The model returned an empty response. Try another GOOGLE_MODEL_NAME.",
            }
        return {"success": True, "description": text, "error": ""}
    except Exception as exc:
        return {
            "success": False,
            "description": "",
            "error": f"AI request failed ({model_name}): {exc}",
        }


def _strip_title_noise(text: str) -> str:
    t = (text or "").strip()
    t = t.strip(' "\'“”')
    # Collapse whitespace; drop lines after first line if model added explanation
    line = t.splitlines()[0].strip() if t else ""
    if len(line) > 80:
        cut = line[:80].rsplit(" ", 1)[0]
        line = cut.rstrip(" ,;:") or line[:80]
    return line


def generate_educational_title(
    title: str,
    transcript: str = "",
    youtube_description: str = "",
) -> dict[str, Any]:
    """
    Return {"success": bool, "title": str, "error": str}.

    Rewrites a noisy YouTube title into a concise educational title (max 80 chars).
    If GOOGLE_API_KEY is missing, returns a clear not-configured message.
    """
    title = (title or "").strip()
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "title": "",
            "error": "AI title rewrite is not configured. Set GOOGLE_API_KEY.",
        }

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()

    yt_desc = (youtube_description or "").strip()
    tr = (transcript or "").strip()
    tr_snip = tr[:12000] if len(tr) > 12000 else tr
    yt_snip = yt_desc[:4000] if len(yt_desc) > 4000 else yt_desc

    prompt = (
        "You are naming a lesson for an automotive electronics education platform. "
        "Rewrite the ORIGINAL TITLE into a clear, classroom-style title. "
        "Remove hashtags, sponsor tags, ALL CAPS clickbait, and filler like “watch this”. "
        "Do not invent topics, tools, vehicle systems, or outcomes that are not clearly supported "
        "by the original title, YouTube description, or transcript excerpt. "
        "Keep it concise. Output ONLY the rewritten title text — no quotes, no numbering, no preamble — "
        "and at most 80 characters.\n\n"
        f"Original title:\n{title or '(none)'}\n\n"
        f"YouTube description (may be empty):\n{yt_snip or '(none)'}\n\n"
        f"Transcript excerpt (may be empty):\n{tr_snip or '(none)'}\n"
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text and getattr(response, "candidates", None):
            parts = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            text = "\n".join(parts).strip()
        if not text:
            return {
                "success": False,
                "title": "",
                "error": "The model returned an empty response. Try another GOOGLE_MODEL_NAME.",
            }
        cleaned = _strip_title_noise(text)
        if not cleaned:
            return {
                "success": False,
                "title": "",
                "error": "The model returned an unusable title.",
            }
        return {"success": True, "title": cleaned, "error": ""}
    except Exception as exc:
        return {
            "success": False,
            "title": "",
            "error": f"AI request failed ({model_name}): {exc}",
        }


def generate_course_public_description(
    course_title: str,
    transcript: str = "",
    book_chunks: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Short public-facing course description from transcript + up to five saved book chunks.

    ``book_chunks`` is a list of (label, excerpt_text) from retrieval (e.g. citation labels).

    Return {"success": bool, "description": str, "error": str}.
    """
    title = (course_title or "").strip()
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "description": "",
            "error": "AI description generation is not configured. Set GOOGLE_API_KEY.",
        }

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()
    tr = (transcript or "").strip()
    tr_snip = tr[:14000] if len(tr) > 14000 else tr

    chunks = book_chunks or []
    chunk_lines: list[str] = []
    for label, text in chunks[:5]:
        lab = (label or "").strip() or "excerpt"
        body = (text or "").strip()
        if not body:
            continue
        body_snip = body[:3500] if len(body) > 3500 else body
        chunk_lines.append(f"[{lab}]\n{body_snip}")
    chunks_blob = "\n\n---\n\n".join(chunk_lines) if chunk_lines else "(none)"

    prompt = (
        "You are writing a short public course description for an automotive / technical education "
        "platform (Car-Hoot). Write 2–4 clear sentences in a professional teaching tone for learners "
        "browsing courses. Base your answer ONLY on the course title, optional training video transcript "
        "excerpt, and optional excerpts from linked book / manual chunks below. "
        "Do not invent credentials, tools, or topics not supported by the materials. "
        "Do not mention chunk labels, retrieval, or AI.\n\n"
        f"Course title:\n{title or '(none)'}\n\n"
        f"Training video transcript excerpt (may be empty):\n{tr_snip or '(none)'}\n\n"
        f"Top book/manual excerpts (may be empty):\n{chunks_blob}\n"
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text and getattr(response, "candidates", None):
            parts = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            text = "\n".join(parts).strip()
        if not text:
            return {
                "success": False,
                "description": "",
                "error": "The model returned an empty response. Try again or adjust GOOGLE_MODEL_NAME.",
            }
        return {"success": True, "description": text, "error": ""}
    except Exception as exc:
        return {
            "success": False,
            "description": "",
            "error": f"AI request failed ({model_name}): {exc}",
        }
