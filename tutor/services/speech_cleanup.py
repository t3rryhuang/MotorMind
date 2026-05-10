"""
Strip citations, markdown, and time references from tutor text for TTS only.
Chat UI should always use the raw assistant reply.
"""

from __future__ import annotations

import re

# Inline reference tags: [V2], [B10], [R3]
_RE_BRACKET_REF = re.compile(r"\[[A-Za-z]{1,12}\d+\]")

# (Book p.42), (Book pp. 42–44)
_RE_BOOK_PAREN = re.compile(
    r"\(\s*Book\s+pp?\.?\s*[\d\s,–\-—]+\s*\)",
    re.IGNORECASE,
)

# (Video 02:31), (Video 2m31s), etc.
_RE_VIDEO_PAREN = re.compile(r"\(\s*Video\s+[^)]+\)", re.IGNORECASE)

# (Source: …)
_RE_SOURCE_PAREN = re.compile(r"\(\s*Source\s*:\s*[^)]+\)", re.IGNORECASE)

# "around 04:18 in the video", "at 1:30 in the video"
_RE_TIME_IN_VIDEO = re.compile(
    r"(?i)\s*(?:,|\s–|\s—)?\s*(?:around|at|from|near)\s+"
    r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:in|from)\s+the\s+video\.?",
)

# "You can see this around … in the video."
_RE_SEE_AROUND_VIDEO = re.compile(
    r"(?i)\s*you can see (?:this|that|it)\b[^.?!]*"
    r"(?:around|at|from|near)\s+\d{1,2}:\d{2}(?::\d{2})?\b[^.?!]*(?:in the video)?[.?!]?",
)

# Standalone clock times (transcript / video refs)
_RE_CLOCK = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

# Markdown / formatting
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_RE_MD_BOLD2 = re.compile(r"__([^_]+)__")
_RE_MD_CODE = re.compile(r"`([^`]+)`")
_RE_MD_ITAL = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_RE_MD_HEAD = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")

# Repeated punctuation
_RE_DUP_PUNCT = re.compile(r"([!?.,:;])\1+")

# Spoken-friendly expansions (word boundaries, case-insensitive)
_SPEAK_ABBREVS: tuple[tuple[str, str], ...] = (
    (r"\bECU\b", "E C U"),
    (r"\bABS\b", "A B S"),
    (r"\bRPM\b", "R P M"),
    (r"\bCAN\b", "C A N"),
    (r"\bOBD\b", "O B D"),
    (r"\bEGR\b", "E G R"),
    (r"\bTCM\b", "T C M"),
    (r"\bPCM\b", "P C M"),
)


def clean_text_for_speech(text: str) -> str:
    """
    Return text safe for ElevenLabs: no bracket refs, book/video/source parens,
    markdown, or clock-style timestamps; light abbreviation expansion for speech.
    """
    if not text:
        return ""
    s = text.strip()

    # Markdown: links → visible anchor text only
    s = _RE_MD_LINK.sub(r"\1", s)
    s = _RE_MD_BOLD.sub(r"\1", s)
    s = _RE_MD_BOLD2.sub(r"\1", s)
    s = _RE_MD_CODE.sub(r"\1", s)
    s = _RE_MD_ITAL.sub(r"\1", s)
    s = _RE_MD_HEAD.sub("", s)

    s = s.replace("**", "").replace("__", "")

    s = _RE_BRACKET_REF.sub("", s)
    s = _RE_BOOK_PAREN.sub("", s)
    s = _RE_VIDEO_PAREN.sub("", s)
    s = _RE_SOURCE_PAREN.sub("", s)

    s = _RE_SEE_AROUND_VIDEO.sub("", s)
    s = _RE_TIME_IN_VIDEO.sub("", s)
    s = _RE_CLOCK.sub("", s)

    # Leftover clause lead-ins after timestamp removal (e.g. "This is discussed")
    s = re.sub(r"(?i)[,.]\s*this is discussed\s*$", "", s)
    s = re.sub(r"(?i)\s+this is discussed\s*$", "", s)

    for pat, repl in _SPEAK_ABBREVS:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)

    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n+", " ", s)
    s = _RE_DUP_PUNCT.sub(r"\1", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+([!?.,:;])", r"\1", s)
    s = re.sub(r"\s+\.", ".", s)
    s = re.sub(r"\s+,", ",", s)
    s = s.strip()

    s = re.sub(r"(^|[.!?]\s+)([,;:–—])+", r"\1", s)
    s = s.strip(" ,;–—")

    if not s:
        s = _RE_BRACKET_REF.sub("", text)
        s = _RE_BOOK_PAREN.sub("", s)
        s = _RE_VIDEO_PAREN.sub("", s)
        s = _RE_SOURCE_PAREN.sub("", s)
        s = re.sub(r"\s+", " ", s).strip()

    return s
