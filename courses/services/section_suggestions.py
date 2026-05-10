"""
Learning-oriented video section suggestions from transcript + caption timestamps.

Uses Gemini when GOOGLE_API_KEY is set; otherwise a deterministic merge into
a small number of sections (hard cap 12).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.db.models import Max

logger = logging.getLogger(__name__)

MAX_SUGGESTED_SECTIONS = 12

_FALLBACK_TITLES = [
    "Introduction and symptoms",
    "Initial diagnostic checks",
    "Testing the circuit",
    "Tracing the fault",
    "Confirming the diagnosis",
    "Repair outcome and recap",
    "Further measurements and scope checks",
    "Wiring diagram walkthrough",
    "Component-level testing",
    "System integration and verification",
    "Common mistakes and pitfalls",
    "Wrap-up and key takeaways",
]


def _fetch_video_duration_seconds(video_url: str) -> int | None:
    url = (video_url or "").strip()
    if not url:
        return None
    try:
        import yt_dlp

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 15,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        d = info.get("duration")
        if d is not None:
            return int(max(1, float(d)))
    except Exception as exc:
        logger.info("yt-dlp duration fetch failed: %s", exc)
    return None


def _target_section_count(duration_s: int | None, n_paragraphs: int) -> int:
    """Prefer 3–5 / 5–8 / 8–12 by video length; never above MAX_SUGGESTED_SECTIONS or paragraph count."""
    if n_paragraphs <= 0:
        return 0
    if duration_s is None or duration_s <= 0:
        duration_s = int(max(120, n_paragraphs * 45))
    if duration_s < 600:
        t = max(3, min(5, 3 + duration_s // 200))
    elif duration_s < 2400:
        t = max(5, min(8, 5 + (duration_s - 600) // 450))
    else:
        t = max(8, min(MAX_SUGGESTED_SECTIONS, 8 + (duration_s - 2400) // 900))
    t = max(1, t)
    return min(n_paragraphs, MAX_SUGGESTED_SECTIONS, t)


def _timing_lines_for_prompt(paras: list[str], starts: list[Any]) -> str:
    lines: list[str] = []
    for i, (p, st) in enumerate(zip(paras, starts)):
        try:
            sec = int(max(0, float(st)))
        except (TypeError, ValueError):
            sec = 0
        snip = (p or "").replace("\n", " ").strip()[:140]
        lines.append(f"P{i + 1}: t={sec}s — {snip}")
    return "\n".join(lines)


def suggest_sections_fallback(
    paras: list[str],
    starts: list[Any],
    *,
    title: str = "",
    duration_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """
    Merge paragraphs into ``target`` contiguous chunks; boundaries snap to paragraph starts.
    """
    n = len(paras)
    if n == 0 or len(starts) != n:
        return []
    int_starts: list[int] = []
    for s in starts:
        try:
            int_starts.append(int(max(0, float(s))))
        except (TypeError, ValueError):
            int_starts.append(0)

    target = _target_section_count(duration_seconds, n)
    if target <= 0:
        target = 1
    target = min(target, n, MAX_SUGGESTED_SECTIONS)

    base = n // target
    rem = n % target
    sections: list[dict[str, Any]] = []
    idx = 0
    for g in range(target):
        size = base + (1 if g < rem else 0)
        if size <= 0:
            continue
        lo = idx
        hi = idx + size - 1
        idx = hi + 1
        start_s = int_starts[lo]
        if hi + 1 < n:
            end_s = max(start_s + 1, int_starts[hi + 1] - 1)
        else:
            tail = int_starts[-1] + max(120, 180)
            if duration_seconds:
                tail = max(tail, duration_seconds)
            end_s = max(start_s + 1, min(tail, 86400 * 24))
        title_i = _FALLBACK_TITLES[len(sections) % len(_FALLBACK_TITLES)]
        sections.append(
            {
                "title": title_i,
                "start_seconds": start_s,
                "end_seconds": min(end_s, 86400 * 24),
                "summary": f"Covers transcript paragraphs {lo + 1}–{hi + 1} (caption-aligned).",
            }
        )
    return sections[:MAX_SUGGESTED_SECTIONS]


def suggest_sections_with_ai(
    *,
    title: str,
    video_url: str,
    transcript: str,
    paras: list[str],
    starts: list[Any],
    duration_seconds: int | None,
) -> dict[str, Any]:
    """Return {success, sections, error}. sections empty on failure."""
    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "sections": [],
            "error": "GOOGLE_API_KEY is not set.",
        }

    target = _target_section_count(duration_seconds, len(paras))
    timing_block = _timing_lines_for_prompt(paras, starts)
    tr_snip = (transcript or "").strip()[:10000]
    dur_note = (
        f"Approximate video duration: {duration_seconds} seconds (from host metadata)."
        if duration_seconds
        else "Video duration unknown; infer sensible section ends from timestamps and transcript."
    )

    prompt = (
        "You design chapter-style sections for an automotive electronics / diagnostics training video. "
        f"Video title: {(title or '').strip() or '(untitled)'}\n"
        f"{dur_note}\n"
        f"Target roughly {target} learning sections (hard maximum {MAX_SUGGESTED_SECTIONS}).\n"
        "Each section must represent a meaningful learning stage, NOT one section per transcript paragraph. "
        "Merge many paragraphs into fewer sections when appropriate.\n"
        "Rules:\n"
        "- Return STRICT JSON: {\"sections\":[{\"title\":...,\"start_seconds\":int,\"end_seconds\":int,\"summary\":...}]}\n"
        "- Section titles: clear educational phrases, about 4–8 words, NOT raw transcript quotes.\n"
        "- start_seconds and end_seconds must be integers; use paragraph timestamp lines below as boundaries "
        "(prefer starts that match a listed P… t=… value).\n"
        "- Sections must be in time order, non-overlapping, each end_seconds > start_seconds.\n"
        "- Do not invent technical facts not grounded in the transcript.\n"
        "- At most 12 sections.\n\n"
        "Paragraph timestamps (reference only; merge into fewer sections):\n"
        f"{timing_block}\n\n"
        f"Transcript (excerpt):\n{tr_snip}\n"
    )

    model_name = (os.environ.get("GOOGLE_MODEL_NAME") or "gemma-3-27b-it").strip()
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
            parts: list[str] = []
            for c in response.candidates:
                for p in getattr(c, "content", None).parts or []:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            raw_text = "\n".join(parts).strip()
        data = json.loads(raw_text)
    except Exception as exc:
        logger.exception("AI section suggestions failed")
        return {"success": False, "sections": [], "error": str(exc)}

    raw_list = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(raw_list, list):
        return {"success": False, "sections": [], "error": "Invalid AI response shape."}

    cleaned: list[dict[str, Any]] = []
    for item in raw_list[:MAX_SUGGESTED_SECTIONS]:
        if not isinstance(item, dict):
            continue
        t = (item.get("title") or "").strip()
        if not t or len(t) > 200:
            continue
        try:
            a = int(item.get("start_seconds", 0))
            b = int(item.get("end_seconds", 0))
        except (TypeError, ValueError):
            continue
        a = max(0, a)
        b = max(0, b)
        if b <= a:
            b = a + 30
        summ = (item.get("summary") or "").strip()[:2000]
        cleaned.append(
            {
                "title": t[:200],
                "start_seconds": min(a, 86400 * 24),
                "end_seconds": min(max(b, a + 1), 86400 * 24),
                "summary": summ,
            }
        )

    cleaned.sort(key=lambda x: x["start_seconds"])

    if not cleaned:
        return {"success": False, "sections": [], "error": "The model returned no usable sections."}

    return {"success": True, "sections": cleaned[:MAX_SUGGESTED_SECTIONS], "error": ""}


def build_section_suggestions(
    *,
    title: str,
    video_url: str,
    transcript: str,
    paragraph_starts: list[Any],
) -> dict[str, Any]:
    """
    Try AI; on missing key or failure, use deterministic fallback.

    Returns:
        success, sections, source ("ai"|"fallback"), error (optional warning/message)
    """
    from courses.services.transcript_formatting import split_transcript_paragraphs

    paras = split_transcript_paragraphs(transcript or "")
    starts = paragraph_starts if isinstance(paragraph_starts, list) else []
    if not paras or len(starts) != len(paras):
        return {
            "success": False,
            "sections": [],
            "source": "none",
            "error": (
                f"Need matching transcript paragraphs and caption timestamps "
                f"({len(paras)} paragraphs, {len(starts)} times). Run YouTube Auto-fill or fix blank-line breaks."
            ),
        }

    duration_s = _fetch_video_duration_seconds(video_url)
    if duration_s is None and starts:
        try:
            duration_s = int(max(int(float(starts[-1])) + 300, 600))
        except (TypeError, ValueError):
            duration_s = 600

    ai = suggest_sections_with_ai(
        title=title,
        video_url=video_url,
        transcript=transcript,
        paras=paras,
        starts=starts,
        duration_seconds=duration_s,
    )
    if ai.get("success") and ai.get("sections"):
        return {
            "success": True,
            "sections": ai["sections"],
            "source": "ai",
            "error": "",
        }

    fb = suggest_sections_fallback(
        paras, starts, title=title, duration_seconds=duration_s
    )
    warn = (ai.get("error") or "").strip() or "Used built-in sectioning (no AI)."
    return {
        "success": True,
        "sections": fb,
        "source": "fallback",
        "error": warn,
    }


def apply_suggested_sections(
    video,
    sections: list[dict[str, Any]],
    *,
    replace: bool,
) -> tuple[int, str | None]:
    """
    Persist VideoSection rows from validated suggestion dicts.

    Each dict: title, start_seconds, end_seconds, summary (optional).
    """
    from courses.models import VideoSection
    from django.db import transaction

    if not isinstance(sections, list) or not sections:
        return 0, "No sections to apply."

    cleaned: list[dict[str, Any]] = []
    for item in sections[:MAX_SUGGESTED_SECTIONS]:
        if not isinstance(item, dict):
            continue
        t = (item.get("title") or "").strip()
        if not t:
            continue
        try:
            a = int(item.get("start_seconds", 0))
            b = int(item.get("end_seconds", 0))
        except (TypeError, ValueError):
            continue
        a = max(0, min(a, 86400 * 24))
        b = max(0, min(b, 86400 * 24))
        if b <= a:
            b = min(a + 60, 86400 * 24)
        cleaned.append(
            {
                "title": t[:255],
                "start_seconds": a,
                "end_seconds": b,
                "summary": ((item.get("summary") or "").strip())[:5000],
            }
        )

    if not cleaned:
        return 0, "No valid sections in payload."

    with transaction.atomic():
        if replace:
            video.sections.all().delete()
            base_order = 0
            to_create = cleaned
        else:
            m = video.sections.aggregate(m=Max("order"))["m"]
            base_order = (m if m is not None else -1) + 1
            existing = {
                (
                    int(s.start_seconds),
                    int(s.end_seconds),
                    (s.title or "").strip().lower(),
                )
                for s in video.sections.all()
            }
            to_create = []
            for row in cleaned:
                key = (
                    int(row["start_seconds"]),
                    int(row["end_seconds"]),
                    row["title"].strip().lower(),
                )
                if key in existing:
                    continue
                to_create.append(row)
                existing.add(key)
            # Idempotent append: nothing new to insert (e.g. table matches DB already).
            if not to_create:
                return (0, None)
        for i, row in enumerate(to_create):
            VideoSection.objects.create(
                video=video,
                title=row["title"],
                start_seconds=row["start_seconds"],
                end_seconds=row["end_seconds"],
                summary=row.get("summary", ""),
                order=base_order + i,
            )
    return len(to_create), None
