from __future__ import annotations

from django.conf import settings
from django.db import models


class CourseReadingContext(models.Model):
    """One retrieval run: transcript query → top-k Chroma chunks saved as evidence."""

    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="reading_contexts",
    )
    video = models.ForeignKey(
        "courses.TrainingVideo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_contexts",
    )
    query_text = models.TextField(help_text="Transcript text used as the similarity query.")
    top_k = models.PositiveSmallIntegerField(default=5)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_contexts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reading context {self.pk} — {self.course_id}"


class CourseReadingSourceChunk(models.Model):
    """A single Chroma hit stored for citation / audit (not full book text)."""

    context = models.ForeignKey(
        CourseReadingContext,
        on_delete=models.CASCADE,
        related_name="source_chunks",
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="reading_source_chunks",
    )
    video = models.ForeignKey(
        "courses.TrainingVideo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_source_chunks",
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_source_chunks",
    )
    vector_id = models.CharField(max_length=256)
    chunk_text = models.TextField()
    score = models.FloatField(null=True, blank=True)
    chunk_index = models.IntegerField(null=True, blank=True)
    page_number = models.IntegerField(null=True, blank=True)
    source_title = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=255, blank=True)
    resource_title = models.CharField(max_length=255, blank=True)
    citation_label = models.CharField(max_length=32, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["context_id", "pk"]


class CourseReadingPage(models.Model):
    """Teacher-editable reading shown on the public course page."""

    course = models.OneToOneField(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="reading_page",
    )
    context = models.ForeignKey(
        CourseReadingContext,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_pages",
    )
    title = models.CharField(max_length=255, blank=True)
    content_html = models.TextField(blank=True)
    editor_json = models.JSONField(default=dict, blank=True)
    citations = models.JSONField(default=list, blank=True)
    diagrams = models.JSONField(default=list, blank=True)
    generated_by_model = models.CharField(max_length=128, blank=True)
    generated_from = models.JSONField(default=dict, blank=True)
    is_teacher_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reading — {self.course_id}"
