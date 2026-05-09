from django.conf import settings
from django.db import models


class Resource(models.Model):
    """
    High-level learning material (PDF, notes, transcript file, etc.).
    Chunk text and vectors live only in ChromaDB — see chunk_count for UI.
    """

    class ResourceType(models.TextChoices):
        BOOK = "book", "Book"
        PDF = "pdf", "PDF"
        TRANSCRIPT = "transcript", "Transcript"
        MANUAL = "manual", "Manual"
        NOTES = "notes", "Notes"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        INGESTING = "ingesting", "Ingesting"
        INGESTED = "ingested", "Ingested"
        FAILED = "failed", "Failed"
        DELETED = "deleted", "Deleted"

    class MetadataLookupStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=255)
    resource_type = models.CharField(
        max_length=32,
        choices=ResourceType.choices,
        default=ResourceType.OTHER,
    )
    uploaded_file = models.FileField(upload_to="resources/")
    original_filename = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    author = models.CharField(max_length=255, blank=True)
    source_title = models.CharField(max_length=255, blank=True)
    edition = models.CharField(max_length=64, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    number_of_pages = models.PositiveIntegerField(null=True, blank=True)
    isbn = models.CharField(max_length=20, blank=True, db_index=True)
    cover_image_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Cached book cover URL (e.g. Open Library), keyed by ISBN.",
    )
    metadata_lookup_status = models.CharField(
        max_length=20,
        choices=MetadataLookupStatus.choices,
        default=MetadataLookupStatus.NOT_REQUIRED,
    )
    metadata_lookup_error = models.TextField(blank=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    courses = models.ManyToManyField(
        "courses.Course",
        related_name="resources",
        blank=True,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_resources",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    vector_collection = models.CharField(max_length=128, default="carhoot_resources")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ResourceIngestionJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="ingestion_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    total_steps = models.PositiveIntegerField(default=0)
    completed_steps = models.PositiveIntegerField(default=0)
    progress_percent = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ingestion {self.pk} — {self.resource.title} ({self.status})"


class ResourceRetrievalLog(models.Model):
    query = models.TextField()
    top_k = models.PositiveIntegerField(default=5)
    results = models.JSONField(default=list)
    searched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_retrieval_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Retrieval {self.pk}: {self.query[:40]}"
