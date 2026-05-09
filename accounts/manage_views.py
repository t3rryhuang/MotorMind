import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
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
from quizzes.services.ai_quiz_suggestions import get_quiz_ai_gate

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

logger = logging.getLogger(__name__)


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


def _refresh_or_reingest_resource_after_course_link(resource_id: int) -> None:
    """
    After Resource.courses changes, refresh Chroma metadata or re-ingest if needed.
    """
    try:
        from resources.models import Resource, ResourceIngestionJob
        from resources.services.ingestion import ingest_resource
        from resources.services.vector_store import refresh_resource_chunk_course_metadata
    except ImportError:
        return

    resource = Resource.objects.prefetch_related("courses").get(pk=resource_id)
    n = refresh_resource_chunk_course_metadata(resource)
    if (
        resource.status == Resource.Status.INGESTED
        and int(resource.chunk_count or 0) > 0
        and n == 0
    ):
        job = ResourceIngestionJob.objects.create(
            resource=resource,
            status=ResourceIngestionJob.Status.QUEUED,
            message="Re-ingest to sync course metadata",
        )
        try:
            ingest_resource(resource.id, job.id)
        except Exception as exc:
            logger.warning("Re-ingest after course link failed: %s", exc)


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
        ctx["resources_module_available"] = False
        ctx["linked_resources"] = []
        ctx["available_resources"] = []
        ctx["linked_book_resources"] = []
        try:
            from resources.models import Resource

            ctx["resources_module_available"] = True
            ctx["linked_resources"] = (
                Resource.objects.filter(courses=course)
                .prefetch_related("courses")
                .order_by("title")
            )
            ctx["available_resources"] = (
                Resource.objects.exclude(courses=course)
                .filter(
                    status__in=[
                        Resource.Status.UPLOADED,
                        Resource.Status.INGESTED,
                        Resource.Status.FAILED,
                    ]
                )
                .order_by("title")
            )
            ctx["linked_book_resources"] = list(
                ctx["linked_resources"].filter(
                    resource_type=Resource.ResourceType.BOOK,
                )
            )
        except ImportError:
            pass
        try:
            from study_content.models import CourseReadingContext, CourseReadingPage

            ctx["study_content_enabled"] = True
            page = CourseReadingPage.objects.filter(course=course).first()
            ctx["course_reading_page"] = page
            latest_ctx = CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
            ctx["reading_chunk_count"] = (
                latest_ctx.source_chunks.count() if latest_ctx else 0
            )
            reading_latest = (
                list(
                    latest_ctx.source_chunks.select_related("resource").order_by(
                        "citation_label", "pk"
                    )
                )
                if latest_ctx
                else []
            )
            ctx["reading_latest_chunks"] = reading_latest
            ctx["reading_chunks_preview"] = [
                {
                    "label": c.citation_label or "",
                    "resource_title": (c.resource_title or c.source_title or "")[:200],
                    "author": (c.author or "")[:200],
                    "page_number": c.page_number,
                    "score": round(float(c.score), 4)
                    if c.score is not None
                    else None,
                    "snippet": (c.chunk_text or "")[:240],
                    "full_text": c.chunk_text or "",
                    "section_title": (
                        ((c.metadata or {}).get("section_title") or "")[:200]
                        if isinstance(c.metadata, dict)
                        else ""
                    ),
                }
                for c in reading_latest
            ]
            if page and (page.content_html or "").strip():
                if page.is_teacher_edited:
                    ctx["reading_status"] = "Edited"
                else:
                    ctx["reading_status"] = "Generated"
            else:
                ctx["reading_status"] = "Not generated"
            ctx["reading_updated"] = getattr(page, "updated_at", None) if page else None
        except ImportError:
            ctx["study_content_enabled"] = False
            ctx["course_reading_page"] = None
            ctx["reading_chunk_count"] = 0
            ctx["reading_status"] = ""
            ctx["reading_updated"] = None
            ctx["reading_latest_chunks"] = []
            ctx["reading_chunks_preview"] = []
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
@require_POST
def video_ai_title_api(request):
    from courses.services.ai_description import generate_educational_title

    if not user_can_use_global_video_tools(request.user):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    out = generate_educational_title(
        title=(body.get("title") or ""),
        transcript=(body.get("transcript") or ""),
        youtube_description=(body.get("youtube_description") or ""),
    )
    return JsonResponse(out)


@login_required
@require_POST
def course_resource_attach(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    raw_rid = (request.POST.get("resource_id") or "").strip()
    if not raw_rid.isdigit():
        messages.error(request, "Choose a resource to attach.")
        return redirect("accounts:manage_course", pk=course_id)
    try:
        from resources.models import Resource
    except ImportError:
        messages.error(request, "Resources are not available in this deployment.")
        return redirect("accounts:manage_course", pk=course_id)

    resource = get_object_or_404(Resource, pk=int(raw_rid))
    resource.courses.add(course)
    _refresh_or_reingest_resource_after_course_link(resource.pk)
    messages.success(request, f"Attached “{resource.title}” to this course.")
    return redirect("accounts:manage_course", pk=course_id)


@login_required
@require_POST
def course_resource_detach(request, course_id, resource_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    try:
        from resources.models import Resource
    except ImportError:
        messages.error(request, "Resources are not available in this deployment.")
        return redirect("accounts:manage_course", pk=course_id)

    resource = get_object_or_404(Resource, pk=resource_id)
    if not resource.courses.filter(pk=course.pk).exists():
        messages.warning(request, "That resource is not linked to this course.")
        return redirect("accounts:manage_course", pk=course_id)
    resource.courses.remove(course)
    _refresh_or_reingest_resource_after_course_link(resource.pk)
    messages.success(
        request,
        f"Detached “{resource.title}” from this course. The resource file was not deleted.",
    )
    return redirect("accounts:manage_course", pk=course_id)


@ensure_csrf_cookie
@login_required
@require_http_methods(["GET", "POST"])
def course_quiz_create(request, course_id):
    """Create a new quiz using the same editor as edit mode (single POST saves all)."""
    course = get_object_or_404(
        _teacher_course_queryset(request.user).prefetch_related("videos"),
        pk=course_id,
    )
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()

    section_options = [
        {"id": s.pk, "label": f"{s.video.title}: {s.title}"}
        for s in VideoSection.objects.filter(video__course_id=course.pk)
        .select_related("video")
        .order_by("video_id", "order", "pk")
    ]
    quiz_initial = {"title": "", "description": "", "pass_mark": 70, "questions": []}

    if request.method == "POST":
        raw = request.POST.get("quiz_payload", "")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON payload.")
        else:
            try:
                with transaction.atomic():
                    quiz = Quiz.objects.create(
                        course=course,
                        title="Untitled",
                        description="",
                        pass_mark=70,
                    )
                    save_quiz_from_payload(quiz, payload, course.pk)
                messages.success(request, "Quiz created.")
                return redirect(
                    "accounts:course_quiz_edit",
                    course_id=course.pk,
                    quiz_id=quiz.pk,
                )
            except QuizEditorSaveError as exc:
                messages.error(request, str(exc))
                quiz_initial = payload

    return render(
        request,
        "quizzes/quiz_editor.html",
        {
            "course": course,
            "quiz": None,
            "section_options": section_options,
            "quiz_initial": quiz_initial,
            "preview_url": "#",
            "back_url": reverse("accounts:manage_course", kwargs={"pk": course.pk}),
            "editor_heading": "Create quiz",
            "editor_mode": "create",
            "ai_suggestions_url": reverse(
                "accounts:course_quiz_ai_suggestions",
                kwargs={"course_id": course.pk},
            ),
            "quiz_ai_gate": get_quiz_ai_gate(course),
        },
    )


@login_required
@require_POST
def course_quiz_ai_suggestions(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    vid = body.get("video_id")
    video_id = None
    if vid is not None and str(vid).strip() not in ("", "null", "None"):
        try:
            video_id = int(vid)
        except (TypeError, ValueError):
            video_id = None
    mode = (body.get("question_count_mode") or "auto").strip().lower()
    qc = body.get("question_count")
    qcount = int(qc) if qc is not None and str(qc).strip().isdigit() else None
    try:
        from quizzes.services.ai_quiz_suggestions import generate_quiz_question_suggestions
    except ImportError:
        return JsonResponse(
            {"success": False, "questions": [], "error": "Quiz AI module unavailable."},
            status=501,
        )
    out = generate_quiz_question_suggestions(
        course,
        video_id=video_id,
        question_count_mode=mode,
        question_count=qcount,
    )
    status = 200 if out.get("success") else 400
    return JsonResponse(out, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def course_quiz_edit(request, course_id, quiz_id):
    course = get_object_or_404(
        _teacher_course_queryset(request.user).prefetch_related("videos"),
        pk=course_id,
    )
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
            "editor_heading": f"Edit {quiz.title}",
            "editor_mode": "edit",
            "ai_suggestions_url": reverse(
                "accounts:course_quiz_ai_suggestions",
                kwargs={"course_id": course.pk},
            ),
            "quiz_ai_gate": get_quiz_ai_gate(course),
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
