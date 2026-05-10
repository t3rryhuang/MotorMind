from django.contrib import admin

from .models import TutorConversation, TutorMessage


class TutorMessageInline(admin.TabularInline):
    model = TutorMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(TutorConversation)
class TutorConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "student", "title", "updated_at")
    list_filter = ("course",)
    inlines = [TutorMessageInline]
