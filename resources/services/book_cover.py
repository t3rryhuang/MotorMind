"""Resolve book cover image URLs from ISBN (Open Library Covers API)."""

from __future__ import annotations

import logging

import requests
from django.core.cache import cache

from resources.services.isbn import clean_isbn, normalise_isbn

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "book_cover_v1"
_CACHE_MISS = "__no_cover__"
_TTL_HIT = 60 * 60 * 24 * 30  # 30 days
_TTL_MISS = 60 * 60 * 24  # 1 day — avoid hammering OL for invalid ISBNs


def openlibrary_cover_url(norm_isbn: str, size: str = "L") -> str:
    return f"https://covers.openlibrary.org/b/isbn/{norm_isbn}-{size}.jpg"


def resource_thumbnail_cover_url(resource) -> str:
    """
    URL for list/thumbnail previews without probing Open Library.

    Uses persisted cover when present; otherwise a small Open Library image
    with default=true so missing covers still show a neutral placeholder.
    """
    from resources.models import Resource

    if not isinstance(resource, Resource):
        return ""
    stored = (resource.cover_image_url or "").strip()
    if stored:
        return stored
    norm = normalise_isbn(clean_isbn(resource.isbn or ""))
    if not norm:
        return ""
    return f"https://covers.openlibrary.org/b/isbn/{norm}-S.jpg?default=true"


def _probe_cover_exists(url: str) -> bool:
    try:
        r = requests.head(
            url,
            params={"default": "false"},
            timeout=8,
            allow_redirects=True,
        )
        return r.status_code == 200 and (r.headers.get("content-type") or "").startswith(
            "image/"
        )
    except requests.RequestException as exc:
        logger.info("Cover probe failed for %s: %s", url, exc)
        return False


def ensure_book_cover_url(resource) -> str:
    """
    Return a stable cover URL for this resource when available.

    Uses Django cache (by ISBN) and persists the URL on the Resource row so
    repeat page loads do not hit Open Library.
    """
    from resources.models import Resource

    if not isinstance(resource, Resource):
        return ""

    stored = (resource.cover_image_url or "").strip()
    if stored:
        return stored

    norm = normalise_isbn(resource.isbn or "")
    if not norm:
        return ""

    cache_key = f"{_CACHE_PREFIX}:{norm}"
    cached = cache.get(cache_key)
    if cached == _CACHE_MISS:
        return ""
    if isinstance(cached, str) and cached.startswith("http"):
        Resource.objects.filter(pk=resource.pk).update(cover_image_url=cached)
        resource.cover_image_url = cached
        return cached

    url = openlibrary_cover_url(norm)
    if not _probe_cover_exists(url):
        cache.set(cache_key, _CACHE_MISS, _TTL_MISS)
        return ""

    cache.set(cache_key, url, _TTL_HIT)
    Resource.objects.filter(pk=resource.pk).update(cover_image_url=url)
    resource.cover_image_url = url
    return url
