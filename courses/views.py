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
                "quizzes",
                "ar_tasks",
            )
            .select_related("created_by")
            .all()
        )


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
