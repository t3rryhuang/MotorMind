from django.conf import settings
from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class TrainingVideo(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="videos",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_url = models.URLField(max_length=500)
    transcript = models.TextField(blank=True)
    # Optional cache from teacher "Auto-fill" / oEmbed (YouTube still works if blank)
    thumbnail_url = models.URLField(max_length=500, blank=True, default="")
    transcript_source = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="e.g. youtube_captions_manual_en when filled from YouTube captions.",
    )
    youtube_description = models.TextField(
        blank=True,
        default="",
        help_text="Optional: YouTube video description for AI context (oEmbed does not provide full text).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title

    @property
    def youtube_video_id(self):
        from .utils import extract_youtube_video_id

        return extract_youtube_video_id(self.video_url or "")

    @property
    def youtube_thumbnail_url(self):
        if self.thumbnail_url:
            return self.thumbnail_url
        from .utils import get_youtube_thumbnail_url

        return get_youtube_thumbnail_url(self.video_url or "")


class VideoSection(models.Model):
    video = models.ForeignKey(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    title = models.CharField(max_length=255)
    start_seconds = models.PositiveIntegerField()
    end_seconds = models.PositiveIntegerField()
    summary = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"{self.video.title}: {self.title}"
