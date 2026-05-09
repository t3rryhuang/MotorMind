"""
Keep Chroma chunk metadata in sync when Resource ↔ Course links change.

Full re-ingestion is not required for M2M updates; see `refresh_resource_chunk_course_metadata`.
"""

from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from courses.models import Course
from resources.models import Resource
from resources.services.vector_store import refresh_resource_chunk_course_metadata

logger = logging.getLogger(__name__)


def _resources_to_refresh(instance, pk_set, action) -> list[Resource]:
    """Resolve affected Resource rows for Resource.courses m2m changes."""
    if isinstance(instance, Resource):
        return [
            Resource.objects.prefetch_related("courses").get(pk=instance.pk),
        ]
    if isinstance(instance, Course):
        if action == "post_clear":
            # Cannot determine removed resource ids reliably here.
            return []
        if pk_set:
            return list(
                Resource.objects.filter(pk__in=pk_set).prefetch_related("courses")
            )
    return []


@receiver(m2m_changed, sender=Resource.courses.through)
def resource_courses_changed_refresh_vectors(sender, instance, action, pk_set, **kwargs):
    if kwargs.get("raw"):
        return
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    for resource in _resources_to_refresh(instance, pk_set, action):
        try:
            n = refresh_resource_chunk_course_metadata(resource)
            if n:
                logger.info(
                    "Refreshed Chroma course metadata for resource_id=%s (%s chunks)",
                    resource.pk,
                    n,
                )
        except Exception:
            logger.exception(
                "Failed to refresh Chroma course metadata for resource_id=%s",
                getattr(resource, "pk", None),
            )
