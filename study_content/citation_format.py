"""Author-surname citations and hover text built from stored chunks."""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from study_content.models import CourseReadingSourceChunk


def author_surname(author: str) -> str:
    """Last name for display: 'Tom Denton' -> 'Denton'; 'Denton, Tom' -> 'Denton'."""
    a = (author or "").strip()
    if not a:
        return "Source"
    if "," in a:
        fam = a.split(",")[0].strip()
        parts = fam.split()
        return parts[-1] if parts else fam
    parts = a.split()
    return parts[-1] if parts else a


def chunk_hover_title(chunk: CourseReadingSourceChunk) -> str:
    """Plain-text tooltip: title, optional section, page."""
    meta: dict[str, Any] = chunk.metadata if isinstance(chunk.metadata, dict) else {}
    section = (meta.get("section_title") or "").strip()
    stitle = (chunk.source_title or chunk.resource_title or "").strip()
    bits: list[str] = []
    if stitle:
        bits.append(stitle)
    if section:
        bits.append(f"Section: {section}")
    if chunk.page_number is not None:
        bits.append(f"Page {chunk.page_number}")
    return " · ".join(bits) if bits else "Book excerpt"


def video_transcript_hover_title(video_title: str) -> str:
    return f"Transcript: {video_title or 'Course videos'}"


def abbr_citation_html(surname: str, hover_title: str, *, video: bool = False) -> str:
    cls = "reading-cite reading-cite--video" if video else "reading-cite"
    return (
        f'<abbr class="{cls}" title="{html.escape(hover_title, quote=True)}">'
        f"{html.escape(surname)}</abbr>"
    )


def replace_label_citations_in_html(
    html_in: str,
    chunks: list[CourseReadingSourceChunk],
    *,
    video_hover: str,
    video_surname: str = "Video",
) -> str:
    """
    Replace [B1]…[B5] and [V1] in model output with <abbr> surname citations.

    Chunks must carry citation_label (e.g. B1).
    """
    out = html_in or ""
    for c in chunks:
        label = (c.citation_label or "").strip()
        if not label:
            continue
        sur = author_surname(c.author or "")
        tip = chunk_hover_title(c)
        rep = abbr_citation_html(sur, tip, video=False)
        pattern = re.compile(re.escape(f"[{label}]"), re.IGNORECASE)
        out = pattern.sub(rep, out)
    vrep = abbr_citation_html(video_surname, video_hover, video=True)
    out = re.sub(r"\[V1\]", vrep, out, flags=re.IGNORECASE)
    return out


def citations_json_from_chunks(
    chunks: list[CourseReadingSourceChunk],
    *,
    video_title: str,
) -> list[dict[str, Any]]:
    """Structured citations for the 'Sources' list (surname + hover fields)."""
    out: list[dict[str, Any]] = []
    for c in chunks:
        meta: dict[str, Any] = c.metadata if isinstance(c.metadata, dict) else {}
        section = (meta.get("section_title") or "").strip()
        out.append(
            {
                "type": "book",
                "surname": author_surname(c.author or ""),
                "hover_title": chunk_hover_title(c),
                "author": c.author or "",
                "source_title": (c.source_title or c.resource_title or "").strip(),
                "page_number": c.page_number,
                "section_title": section,
            }
        )
    out.append(
        {
            "type": "video",
            "surname": "Video",
            "hover_title": video_transcript_hover_title(video_title),
            "video_title": video_title or "Course videos",
        }
    )
    return out
