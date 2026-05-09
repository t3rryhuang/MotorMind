"""Template helpers for resource UI."""

from __future__ import annotations

from django import template

from resources.services.book_cover import resource_thumbnail_cover_url

register = template.Library()


@register.filter
def resource_cover_thumb(resource) -> str:
    """Small cover URL (stored probe URL or Open Library with default image)."""
    return resource_thumbnail_cover_url(resource)
