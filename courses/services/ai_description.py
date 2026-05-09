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
