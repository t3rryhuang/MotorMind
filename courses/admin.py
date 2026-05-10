from django.contrib import admin
from django.templatetags.static import static
from django.utils.html import format_html

from .models import Course, TrainingVideo, VideoSection


class VideoSectionInline(admin.TabularInline):
    model = VideoSection
    extra = 0


class TrainingVideoInline(admin.StackedInline):
    model = TrainingVideo
    extra = 0
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("icon_thumb", "title", "icon_name", "created_by", "created_at")
    search_fields = ("title",)

    def icon_thumb(self, obj):
        url = static(obj.icon_static_path)
        return format_html(
            '<img src="{}" width="28" height="28" style="border-radius:50%;object-fit:cover" alt="" />',
            url,
        )

    icon_thumb.short_description = "Icon"

    inlines = [TrainingVideoInline]


@admin.register(TrainingVideo)
class TrainingVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "created_at")
    list_filter = ("course",)
    inlines = [VideoSectionInline]


@admin.register(VideoSection)
class VideoSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "video", "start_seconds", "end_seconds", "order")
    list_filter = ("video__course",)
