from django.conf import settings
from django.db import models

from .course_icons import COURSE_ICON_SLUGS


class Course(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    icon_name = models.CharField(
        max_length=80,
        blank=True,
        default="diagnostics",
        help_text="Basename of SVG under static/images/course-icons/ (no extension).",
    )
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

    @property
    def icon_static_path(self) -> str:
        """Static path relative to STATIC_URL for {% static %}; invalid/blank → default.svg."""
        slug = (self.icon_name or "").strip()
        if slug in COURSE_ICON_SLUGS:
            return f"images/course-icons/{slug}.svg"
        return "images/course-icons/default.svg"


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
    transcript_paragraph_starts = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Integer start seconds per transcript paragraph (split by blank lines), "
            "from YouTube caption timing — not embedded in transcript text."
        ),
    )
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
    def youtube_embed_url(self) -> str:
        """Base YouTube iframe embed URL, or empty string if not a YouTube link."""
        vid = self.youtube_video_id
        if not vid:
            return ""
        return f"https://www.youtube.com/embed/{vid}"

    @property
    def youtube_thumbnail_url(self):
        if self.thumbnail_url:
            return self.thumbnail_url
        from .utils import get_youtube_thumbnail_url

        return get_youtube_thumbnail_url(self.video_url or "")

    def reconcile_transcript_paragraph_starts(self) -> None:
        """Clear or clamp stored times when paragraph count does not match transcript."""
        from courses.services.transcript_formatting import split_transcript_paragraphs

        paras = split_transcript_paragraphs(self.transcript or "")
        starts = self.transcript_paragraph_starts
        if not isinstance(starts, list) or len(starts) != len(paras):
            self.transcript_paragraph_starts = []
            return
        clean: list[int] = []
        for x in starts:
            try:
                clean.append(int(max(0, min(86400, float(x)))))
            except (TypeError, ValueError):
                clean.append(0)
        self.transcript_paragraph_starts = clean

    def save(self, *args, **kwargs):
        self.reconcile_transcript_paragraph_starts()
        super().save(*args, **kwargs)


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
