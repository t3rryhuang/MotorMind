"""
Lightweight YouTube caption → readable prose (no LLM).

Joins short caption lines, removes common non-speech tokens, splits into
paragraphs using sentence boundaries, transition words, and length limits.
"""

from __future__ import annotations

import re
from typing import Any

# Inline / bracketed caption noise (case-insensitive where noted)
_NOISE_RE = re.compile(
    r"(?i)\[+\s*music\s*\]+|\(+music\)|\[\s*applause\s*\]|\[\s*crowd\s*\]|"
    r">>\s*\[+\s*music\s*\]+|>>\s*\(+music\)|♪+|♫+"
)

# Sentence split: period / question / exclamation followed by space + lookahead
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=\S)")

# New paragraph when a sentence starts with these (word boundary, case-insensitive)
_TRANSITION_RE = re.compile(
    r"^(Right|Okay|Ok|So|Now|Next|Then|Finally|First|Secondly|Third|"
    r"Therefore|However|Anyway|Well|Alright|All right)\b",
    re.IGNORECASE,
)

_PARA_MIN_CHARS = 500
_PARA_MAX_CHARS = 700
_TARGET_SENTENCES_PER_PARA = 4  # aim ~3–5


def _normalize_whitespace(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _NOISE_RE.sub(" ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n+", " ", t)
    return t.strip()


def _split_sentences(text: str) -> list[str]:
    """Rough sentence split on . ? ! followed by space."""
    t = text.strip()
    if not t:
        return []
    parts = _SENT_SPLIT_RE.split(t)
    if len(parts) == 1:
        return [parts[0].strip()] if parts[0].strip() else []
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out


def _split_oversized_sentence(sentence: str, max_len: int) -> list[str]:
    """Hard-wrap very long sentences at word boundaries for paragraph limits."""
    if len(sentence) <= max_len:
        return [sentence]
    chunks: list[str] = []
    rest = sentence
    while len(rest) > max_len:
        cut = rest.rfind(" ", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def format_transcript_for_reading(raw_text: str) -> str:
    """
    Turn raw caption text into paragraphs separated by blank lines.

    Rules: normalize whitespace, strip music-style noise, join fragments,
    split on sentence punctuation, new paragraph every ~3–5 sentences or on
    transition words at sentence start, cap paragraph length ~500–700 chars.
    """
    text = _normalize_whitespace(raw_text)
    if not text:
        return ""

    sentences = _split_sentences(text)
    expanded: list[str] = []
    for s in sentences:
        expanded.extend(_split_oversized_sentence(s, _PARA_MAX_CHARS))

    paragraphs: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            paragraphs.append(" ".join(buf))
            buf = []
            buf_len = 0

    for sent in expanded:
        st = sent.strip()
        if not st:
            continue
        if _TRANSITION_RE.match(st) and buf:
            flush()
        buf.append(st)
        buf_len += len(st) + 1
        sent_count = len(buf)
        if sent_count >= _TARGET_SENTENCES_PER_PARA and buf_len >= _PARA_MIN_CHARS:
            flush()
        elif buf_len >= _PARA_MAX_CHARS:
            flush()

    flush()

    # Merge tiny tail paragraphs into previous
    if len(paragraphs) >= 2 and len(paragraphs[-1]) < 120:
        paragraphs[-2] = paragraphs[-2] + " " + paragraphs[-1]
        paragraphs.pop()

    return "\n\n".join(p for p in paragraphs if p.strip())


def format_transcript_segments(segments: list[dict[str, Any]]) -> str:
    """Join segment texts in order, then apply `format_transcript_for_reading`."""
    parts: list[str] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        t = (seg.get("text") or "").replace("\n", " ").strip()
        if t:
            parts.append(t)
    joined = " ".join(parts)
    return format_transcript_for_reading(joined)
