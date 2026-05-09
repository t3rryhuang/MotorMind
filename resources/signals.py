"""
Keep Chroma chunk metadata in sync when Resource ↔ Course links change.

Full re-ingestion is not required for M2M updates; see `refresh_resource_chunk_course_metadata`.
"""

from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from resources.models import Resource
from resources.services.vector_store import refresh_resource_chunk_course_metadata

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=Resource.courses.through)
def resource_courses_changed_refresh_vectors(sender, instance, action, **kwargs):
    if kwargs.get("raw"):
        return
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not isinstance(instance, Resource):
        return
    try:
        n = refresh_resource_chunk_course_metadata(instance)
        if n:
            logger.info(
                "Refreshed Chroma course metadata for resource_id=%s (%s chunks)",
                instance.pk,
                n,
            )
    except Exception:
        logger.exception(
            "Failed to refresh Chroma course metadata for resource_id=%s",
            getattr(instance, "pk", None),
        )
