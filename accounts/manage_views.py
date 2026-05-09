import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import CreateView, UpdateView

from ar_tasks.models import ARTask, ARTaskStep
from courses.models import Course, TrainingVideo, VideoSection
from quizzes.models import Question, Quiz
from quizzes.quiz_editor_save import QuizEditorSaveError, quiz_to_editor_payload, save_quiz_from_payload

from .forms import (
    AnswerChoiceForm,
    ARTaskForm,
    ARTaskStepForm,
    CourseForm,
    QuestionForm,
    QuizForm,
    TrainingVideoEditForm,
    TrainingVideoForm,
    VideoSectionForm,
)
from .mixins import TeacherRequiredMixin
from .models import Profile


def user_can_manage_course(user, course) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    if profile is None or profile.role != Profile.Role.TEACHER:
        return False
    return course.created_by_id == user.pk


def _teacher_course_queryset(user):
    qs = Course.objects.all()
    if not (user.is_superuser or user.is_staff):
        qs = qs.filter(created_by=user)
    return qs


def user_can_use_global_video_tools(user) -> bool:
    """Teachers and staff may call YouTube autofill / AI description JSON endpoints."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    return profile is not None and profile.role == Profile.Role.TEACHER


class BaseManageCreateView(TeacherRequiredMixin, CreateView):
    """Teacher create views: default cancel returns to admin panel."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("cancel_url", reverse("accounts:admin_panel"))
        return ctx


class NestedCourseManageMixin:
    """Require `course_pk` in URL; course must belong to the current teacher."""

    course_pk_url_kwarg = "course_pk"

    def dispatch(self, request, *args, **kwargs):
        cid = int(kwargs[self.course_pk_url_kwarg])
        qs = Course.objects.all()
        if not (request.user.is_superuser or request.user.is_staff):
            qs = qs.filter(created_by=request.user)
        self.nested_course = get_object_or_404(qs, pk=cid)
        self.nested_course_id = cid
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancel_url"] = reverse("accounts:manage_course", kwargs={"pk": self.nested_course_id})
        return ctx

    def get_success_url(self):
        return reverse("accounts:manage_course", kwargs={"pk": self.nested_course_id})


class CourseHubView(TeacherRequiredMixin, UpdateView):
    """
    Edit course metadata and jump off to add videos, sections, quizzes, AR tasks
    scoped to this course.
    """

    model = Course
    form_class = CourseForm
    template_name = "accounts/manage/course_hub.html"
    context_object_name = "course"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return Course.objects.all()
        return Course.objects.filter(created_by=user)

    def get_success_url(self):
        return reverse("accounts:manage_course", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        course = self.object
        ctx["videos"] = course.videos.prefetch_related("sections").order_by("created_at")
        from django.db.models import Count

        ctx["quizzes"] = (
            course.quizzes.annotate(num_questions=Count("questions", distinct=True))
            .order_by("pk")
        )
        ctx["ar_tasks"] = course.ar_tasks.order_by("pk")
        ctx["cancel_url"] = reverse("accounts:admin_panel")
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Course saved.")
        return super().form_valid(form)


class CourseCreateView(BaseManageCreateView):
    form_class = CourseForm
    template_name = "accounts/manage/course_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Course created — add videos, quizzes, and AR tasks below.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("accounts:manage_course", kwargs={"pk": self.object.pk})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class TrainingVideoCreateView(BaseManageCreateView):
    form_class = TrainingVideoForm
    template_name = "accounts/manage/training_video_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Add training video"
        ctx["show_course_field"] = True
        return ctx

    def get_success_url(self):
        return reverse("accounts:admin_panel")


@method_decorator(ensure_csrf_cookie, name="dispatch")
class NestedTrainingVideoCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = TrainingVideoForm
    template_name = "accounts/manage/training_video_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Add training video"
        ctx["show_course_field"] = True
        return ctx

    def get_initial(self):
        return {**super().get_initial(), "course": self.nested_course_id}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["course"].queryset = Course.objects.filter(pk=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Video added.")
        return super().form_valid(form)


class NestedCourseByIdMixin(NestedCourseManageMixin):
    """Same as NestedCourseManageMixin but URL kwarg is `course_id`."""

    course_pk_url_kwarg = "course_id"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class NestedTrainingVideoUpdateView(NestedCourseByIdMixin, TeacherRequiredMixin, UpdateView):
    model = TrainingVideo
    form_class = TrainingVideoEditForm
    template_name = "accounts/manage/training_video_editor.html"
    pk_url_kwarg = "video_id"
    context_object_name = "video"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit training video"
        ctx["show_course_field"] = False
        return ctx

    def get_queryset(self):
        return TrainingVideo.objects.filter(course_id=self.nested_course_id)

    def form_valid(self, form):
        messages.success(self.request, "Video updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("accounts:manage_course", kwargs={"pk": self.nested_course_id})


class VideoSectionCreateView(BaseManageCreateView):
    form_class = VideoSectionForm
    template_name = "accounts/manage/video_section_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedVideoSectionCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = VideoSectionForm
    template_name = "accounts/manage/video_section_form.html"

    def get_initial(self):
        initial = super().get_initial()
        vid = self.request.GET.get("video")
        if vid and str(vid).isdigit():
            vpk = int(vid)
            if TrainingVideo.objects.filter(pk=vpk, course_id=self.nested_course_id).exists():
                initial["video"] = vpk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["video"].queryset = TrainingVideo.objects.filter(course_id=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Section added.")
        return super().form_valid(form)


class QuizCreateView(BaseManageCreateView):
    form_class = QuizForm
    template_name = "accounts/manage/quiz_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedQuizCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = QuizForm
    template_name = "accounts/manage/quiz_form.html"

    def get_initial(self):
        return {**super().get_initial(), "course": self.nested_course_id}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["course"].queryset = Course.objects.filter(pk=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Quiz added.")
        return super().form_valid(form)


class QuestionCreateView(BaseManageCreateView):
    form_class = QuestionForm
    template_name = "accounts/manage/question_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedQuestionCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = QuestionForm
    template_name = "accounts/manage/question_form.html"

    def get_initial(self):
        initial = super().get_initial()
        qid = self.request.GET.get("quiz")
        if qid and str(qid).isdigit():
            qpk = int(qid)
            if Quiz.objects.filter(pk=qpk, course_id=self.nested_course_id).exists():
                initial["quiz"] = qpk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["quiz"].queryset = Quiz.objects.filter(course_id=self.nested_course_id)
        form.fields["section"].queryset = VideoSection.objects.filter(video__course_id=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Question added.")
        return super().form_valid(form)


class AnswerChoiceCreateView(BaseManageCreateView):
    form_class = AnswerChoiceForm
    template_name = "accounts/manage/answer_choice_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedAnswerChoiceCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = AnswerChoiceForm
    template_name = "accounts/manage/answer_choice_form.html"

    def get_initial(self):
        initial = super().get_initial()
        qid = self.request.GET.get("question")
        if qid and str(qid).isdigit():
            qpk = int(qid)
            if Question.objects.filter(pk=qpk, quiz__course_id=self.nested_course_id).exists():
                initial["question"] = qpk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["question"].queryset = Question.objects.filter(quiz__course_id=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Answer choice added.")
        return super().form_valid(form)


class ARTaskCreateView(BaseManageCreateView):
    form_class = ARTaskForm
    template_name = "accounts/manage/ar_task_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedARTaskCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = ARTaskForm
    template_name = "accounts/manage/ar_task_form.html"

    def get_initial(self):
        return {**super().get_initial(), "course": self.nested_course_id}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["course"].queryset = Course.objects.filter(pk=self.nested_course_id)
        form.fields["linked_video_section"].queryset = VideoSection.objects.filter(
            video__course_id=self.nested_course_id
        )
        return form

    def form_valid(self, form):
        messages.success(self.request, "AR task added.")
        return super().form_valid(form)


class ARTaskStepCreateView(BaseManageCreateView):
    form_class = ARTaskStepForm
    template_name = "accounts/manage/ar_task_step_form.html"

    def get_success_url(self):
        return reverse("accounts:admin_panel")


class NestedARTaskStepCreateView(NestedCourseManageMixin, BaseManageCreateView):
    form_class = ARTaskStepForm
    template_name = "accounts/manage/ar_task_step_form.html"

    def get_initial(self):
        initial = super().get_initial()
        tid = self.request.GET.get("task")
        if tid and str(tid).isdigit():
            tpk = int(tid)
            if ARTask.objects.filter(pk=tpk, course_id=self.nested_course_id).exists():
                initial["task"] = tpk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["task"].queryset = ARTask.objects.filter(course_id=self.nested_course_id)
        return form

    def form_valid(self, form):
        messages.success(self.request, "AR step added.")
        return super().form_valid(form)


@login_required
@require_POST
def video_youtube_autofill_api(request):
    from courses.services.youtube import build_youtube_autofill_response

    if not user_can_use_global_video_tools(request.user):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    video_url = (body.get("video_url") or "").strip()
    try:
        payload = build_youtube_autofill_response(video_url)
    except Exception as exc:
        return JsonResponse(
            {"success": False, "error": f"Auto-fill failed: {exc}"},
            status=500,
        )
    return JsonResponse(
        {
            "success": payload["success"],
            "title": payload.get("title") or "",
            "youtube_description": payload.get("youtube_description") or "",
            "thumbnail_url": payload.get("thumbnail_url") or "",
            "transcript": payload.get("transcript") or "",
            "transcript_source": payload.get("transcript_source") or "",
            "transcript_source_code": payload.get("transcript_source_code") or "",
            "warnings": payload.get("warnings") or [],
        }
    )


@login_required
@require_POST
def video_ai_description_api(request):
    from courses.services.ai_description import generate_video_description

    if not user_can_use_global_video_tools(request.user):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    out = generate_video_description(
        title=(body.get("title") or ""),
        youtube_description=(body.get("youtube_description") or ""),
        transcript=(body.get("transcript") or ""),
    )
    return JsonResponse(out)


@login_required
@require_http_methods(["GET", "POST"])
def course_quiz_edit(request, course_id, quiz_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()

    quiz = get_object_or_404(
        Quiz.objects.filter(pk=quiz_id, course_id=course_id).prefetch_related(
            Prefetch(
                "questions",
                queryset=Question.objects.order_by("order", "pk").prefetch_related("choices"),
            )
        ),
        pk=quiz_id,
    )

    section_options = [
        {"id": s.pk, "label": f"{s.video.title}: {s.title}"}
        for s in VideoSection.objects.filter(video__course_id=course.pk)
        .select_related("video")
        .order_by("video_id", "order", "pk")
    ]

    quiz_initial = quiz_to_editor_payload(quiz)
    if request.method == "POST":
        raw = request.POST.get("quiz_payload", "")
        try:
            payload = json.loads(raw)
            save_quiz_from_payload(quiz, payload, course.pk)
            messages.success(request, "Quiz saved.")
            return redirect(
                "accounts:course_quiz_edit",
                course_id=course.pk,
                quiz_id=quiz.pk,
            )
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON payload.")
        except QuizEditorSaveError as exc:
            messages.error(request, str(exc))
            try:
                quiz_initial = json.loads(raw)
            except json.JSONDecodeError:
                quiz_initial = quiz_to_editor_payload(quiz)

    return render(
        request,
        "quizzes/quiz_editor.html",
        {
            "course": course,
            "quiz": quiz,
            "section_options": section_options,
            "quiz_initial": quiz_initial,
            "preview_url": reverse("quizzes:quiz_take", kwargs={"quiz_id": quiz.pk}),
            "back_url": reverse("accounts:manage_course", kwargs={"pk": course.pk}),
        },
    )


@login_required
@require_POST
def course_quiz_delete(request, course_id, quiz_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    quiz = get_object_or_404(Quiz, pk=quiz_id, course_id=course_id)
    title = quiz.title
    quiz.delete()
    messages.success(request, f'Deleted quiz "{title}".')
    return redirect("accounts:manage_course", pk=course_id)


@login_required
@require_POST
def course_training_video_delete(request, course_id, video_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    video = get_object_or_404(TrainingVideo, pk=video_id, course_id=course_id)
    title = video.title
    video.delete()
    messages.success(request, f'Deleted video "{title}".')
    return redirect("accounts:manage_course", pk=course_id)
