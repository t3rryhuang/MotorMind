"""
Teacher workflows: course reading chunks, generation, editor, preview.
"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Profile
from courses.models import Course, TrainingVideo

from study_content.models import CourseReadingContext, CourseReadingPage
from study_content.services.generation import generate_course_reading
from study_content.services.retrieval import RetrievalError, select_top_chunks_for_course_reading
from study_content.utils_html import sanitize_reading_html

logger = logging.getLogger(__name__)


def _teacher_course_queryset(user):
    qs = Course.objects.all()
    if not (user.is_superuser or user.is_staff):
        qs = qs.filter(created_by=user)
    return qs


def user_can_manage_course(user, course) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    if profile is None or profile.role != Profile.Role.TEACHER:
        return False
    return course.created_by_id == user.pk


@login_required
@require_POST
def reading_find_chunks(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    vid = (request.POST.get("video_id") or "").strip()
    video = None
    if vid.isdigit():
        video = TrainingVideo.objects.filter(pk=int(vid), course_id=course.pk).first()
    try:
        select_top_chunks_for_course_reading(
            course, video=video, top_k=5, user=request.user
        )
        messages.success(request, "Top similarity chunks saved for this course.")
    except RetrievalError as exc:
        messages.error(request, exc.message)
    except Exception as exc:
        logger.exception("reading_find_chunks failed")
        messages.error(request, f"Chunk retrieval failed: {exc}")
    return redirect("accounts:manage_course", pk=course.pk)


@login_required
@require_POST
def reading_generate(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    ctx = CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
    if ctx is None or not ctx.source_chunks.exists():
        try:
            ctx = select_top_chunks_for_course_reading(course, video=None, top_k=5, user=request.user)
        except RetrievalError as exc:
            messages.error(request, exc.message)
            return redirect("accounts:manage_course", pk=course.pk)
        except Exception as exc:
            logger.exception("reading_generate auto-retrieve failed")
            messages.error(request, str(exc))
            return redirect("accounts:manage_course", pk=course.pk)
    try:
        generate_course_reading(course, ctx, user=request.user)
        messages.success(request, "Reading section generated. Review and edit before publishing.")
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception("reading_generate failed")
        messages.error(request, f"Generation failed: {exc}")
    return redirect("accounts:manage_course", pk=course.pk)


@login_required
@require_http_methods(["GET", "POST"])
def reading_edit(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()

    page, _ = CourseReadingPage.objects.get_or_create(course=course)
    latest_ctx = CourseReadingContext.objects.filter(course=course).order_by("-pk").first()
    source_chunks = (
        list(latest_ctx.source_chunks.all()) if latest_ctx else []
    )

    if request.method == "POST":
        page.title = (request.POST.get("title") or "").strip()[:255]
        page.content_html = request.POST.get("content_html") or ""
        try:
            page.citations = json.loads(request.POST.get("citations_json") or "[]")
        except json.JSONDecodeError:
            page.citations = []
        try:
            page.diagrams = json.loads(request.POST.get("diagrams_json") or "[]")
        except json.JSONDecodeError:
            page.diagrams = []
        page.is_teacher_edited = True
        page.save()
        messages.success(request, "Reading saved.")
        return redirect("accounts:manage_course", pk=course.pk)

    return render(
        request,
        "study_content/reading_editor.html",
        {
            "course": course,
            "page": page,
            "latest_context": latest_ctx,
            "source_chunks": source_chunks,
            "citations_json": json.dumps(page.citations or [], indent=2),
            "diagrams_json": json.dumps(page.diagrams or [], indent=2),
            "preview_html": sanitize_reading_html(page.content_html or ""),
            "back_url": reverse("accounts:manage_course", kwargs={"pk": course.pk}),
        },
    )


@login_required
def reading_preview(request, course_id):
    course = get_object_or_404(_teacher_course_queryset(request.user), pk=course_id)
    if not user_can_manage_course(request.user, course):
        return HttpResponseForbidden()
    page = CourseReadingPage.objects.filter(course=course).first()
    if not page or not (page.content_html or "").strip():
        messages.info(request, "No reading content to preview yet.")
        return redirect("accounts:manage_course", pk=course.pk)
    return render(
        request,
        "study_content/reading_preview.html",
        {
            "course": course,
            "page": page,
            "reading_html_safe": sanitize_reading_html(page.content_html or ""),
            "back_url": reverse("accounts:manage_course", kwargs={"pk": course.pk}),
        },
    )
