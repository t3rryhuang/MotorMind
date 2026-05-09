"""Sanitize teacher-authored reading HTML for student display."""

from __future__ import annotations

import re

import bleach


def sanitize_reading_html(html: str) -> str:
    """
    Allow a practical subset of tags for structured readings + diagram placeholders.

    Teachers are trusted; this still strips scripts/on* handlers and unexpected tags.
    """
    raw = html or ""
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", "", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", "", raw)
    allowed_tags = bleach.sanitizer.ALLOWED_TAGS.union(
        {
            "p",
            "div",
            "span",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "strong",
            "em",
            "b",
            "i",
            "br",
            "hr",
            "blockquote",
            "pre",
            "code",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "a",
            "section",
            "article",
            "abbr",
        }
    )
    allowed_attrs = {
        "*": ["class", "id"],
        "a": ["href", "title", "rel", "target"],
        "abbr": ["title", "class"],
        "div": ["class", "id", "data-diagram-id"],
    }
    return bleach.clean(
        raw,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
