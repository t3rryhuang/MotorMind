from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView, TemplateView

from .models import Course, TrainingVideo
from .utils import extract_youtube_video_id


class LandingView(TemplateView):
    template_name = "courses/landing.html"


class CourseListView(LoginRequiredMixin, ListView):
    model = Course
    template_name = "courses/course_list.html"
    context_object_name = "courses"


class CourseDetailView(LoginRequiredMixin, DetailView):
    model = Course
    template_name = "courses/course_detail.html"
    context_object_name = "course"

    def get_queryset(self):
        return (
            Course.objects.prefetch_related(
                "videos",
                "videos__sections",
                "quizzes",
                "ar_tasks",
            )
            .select_related("created_by")
            .all()
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["course_reading_page"] = None
        ctx["course_reading_html"] = ""
        ctx["course_reading_title"] = ""
        ctx["course_reading_diagrams_json"] = "[]"
        try:
            from study_content.models import CourseReadingPage
            from study_content.utils_html import sanitize_reading_html

            page = CourseReadingPage.objects.filter(course=self.object).first()
            if page and (page.content_html or "").strip():
                ctx["course_reading_page"] = page
                ctx["course_reading_html"] = sanitize_reading_html(page.content_html)
                ctx["course_reading_title"] = page.title or f"{self.object.title} reading"
                ctx["course_reading_diagrams"] = page.diagrams or []
        except ImportError:
            pass
        return ctx


def parse_video_start_seconds(request_get):
    """Read `t` query param for jump-to-time (seconds)."""
    raw = request_get.get("t") or request_get.get("start") or "0"
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return 0


class VideoDetailView(LoginRequiredMixin, DetailView):
    model = TrainingVideo
    template_name = "courses/video_detail.html"
    context_object_name = "video"
    pk_url_kwarg = "video_id"

    def get_queryset(self):
        cid = self.kwargs["course_id"]
        return (
            TrainingVideo.objects.filter(course_id=cid)
            .select_related("course")
            .prefetch_related("sections")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start = parse_video_start_seconds(self.request.GET)
        ctx["start_seconds"] = start
        ctx["youtube_id"] = extract_youtube_video_id(self.object.video_url or "") or None
        return ctx
