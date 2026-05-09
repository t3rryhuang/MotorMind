from django.urls import path

from . import views

app_name = "study_content"

urlpatterns = [
    path(
        "manage/course/<int:course_id>/reading/find-chunks/",
        views.reading_find_chunks,
        name="reading_find_chunks",
    ),
    path(
        "manage/course/<int:course_id>/reading/generate/",
        views.reading_generate,
        name="reading_generate",
    ),
    path(
        "manage/course/<int:course_id>/reading/edit/",
        views.reading_edit,
        name="reading_edit",
    ),
    path(
        "manage/course/<int:course_id>/reading/preview/",
        views.reading_preview,
        name="reading_preview",
    ),
]
