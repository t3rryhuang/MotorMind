from django.contrib import admin

from .models import CourseReadingContext, CourseReadingPage, CourseReadingSourceChunk


class SourceChunkInline(admin.TabularInline):
    model = CourseReadingSourceChunk
    extra = 0
    readonly_fields = ("vector_id", "chunk_text", "score", "citation_label")


@admin.register(CourseReadingContext)
class CourseReadingContextAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "video", "top_k", "created_at")
    inlines = [SourceChunkInline]


@admin.register(CourseReadingPage)
class CourseReadingPageAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "is_teacher_edited", "updated_at")


@admin.register(CourseReadingSourceChunk)
class CourseReadingSourceChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "context", "citation_label", "resource", "score", "created_at")
