"""
Teacher-facing HTML workflows for resource library + retrieval testing.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, FormView, ListView, UpdateView

from accounts.mixins import TeacherRequiredMixin

from .forms import MinimalResourceUploadForm, ResourceEditForm
from .models import Resource, ResourceIngestionJob, ResourceRetrievalLog
from .serializers_api import ResourceDetailSerializer
from .services.book_cover import ensure_book_cover_url
from .services.isbn import clean_isbn, normalise_isbn
from .services.resource_upload import apply_metadata_lookup_to_resource, build_resource_from_minimal_upload
from .services.ingestion import ingest_resource
from .services.search_format import format_api_results
from .services.vector_store import delete_resource_vectors, query_similar_chunks

logger = logging.getLogger(__name__)


class ResourceDashboardView(TeacherRequiredMixin, ListView):
    model = Resource
    template_name = "resources/dashboard.html"
    context_object_name = "resources"

    def get_queryset(self):
        return Resource.objects.prefetch_related("courses").order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["upload_form"] = MinimalResourceUploadForm()
        return ctx


class ResourceUploadView(TeacherRequiredMixin, FormView):
    form_class = MinimalResourceUploadForm

    def get(self, request, *args, **kwargs):
        return redirect("resources:dashboard")

    def form_valid(self, form):
        f = form.cleaned_data["uploaded_file"]
        fname = getattr(f, "name", "") or ""
        explicit = form.cleaned_data.get("resource_type") or ""
        try:
            resource = build_resource_from_minimal_upload(
                uploaded_file=f,
                original_filename=fname,
                explicit_resource_type=explicit,
                user=self.request.user,
            )
            resource.uploaded_file = f
            resource.save()
        except ValidationError as exc:
            for msg in getattr(exc, "messages", [str(exc)]):
                form.add_error("uploaded_file", msg)
            return self.form_invalid(form)

        resource.courses.set(form.cleaned_data.get("courses") or [])

        job = ResourceIngestionJob.objects.create(
            resource=resource,
            status=ResourceIngestionJob.Status.QUEUED,
            message="Queued",
        )
        try:
            ingest_resource(resource.id, job.id)
            messages.success(self.request, f"Ingested “{resource.title}”.")
        except Exception as exc:  # pragma: no cover - surfaced to UI
            logger.exception("Upload ingest failed")
            messages.error(self.request, f"Ingestion failed: {exc}")
            if self._wants_json():
                resource.refresh_from_db()
                return JsonResponse(
                    {
                        "resource_id": resource.id,
                        "job_id": job.id,
                        "detail": str(exc),
                        "status": resource.status,
                    },
                    status=500,
                )
            return redirect("resources:detail", pk=resource.pk)

        if self._wants_json():
            resource.refresh_from_db()
            return JsonResponse(
                {
                    "resource_id": resource.id,
                    "job_id": job.id,
                    "redirect_url": reverse("resources:detail", kwargs={"pk": resource.id})
                    + f"?job={job.id}",
                    "status": resource.status,
                    "resource": ResourceDetailSerializer(resource).data,
                }
            )
        return redirect("resources:detail", pk=resource.pk)

    def form_invalid(self, form):
        if self._wants_json():
            err_msg = None
            for _field, errs in form.errors.items():
                if errs:
                    err_msg = str(errs[0])
                    break
            return JsonResponse(
                {"error": err_msg or "Invalid upload.", "errors": form.errors},
                status=400,
            )
        from django.shortcuts import render

        resources = Resource.objects.prefetch_related("courses").order_by("-created_at")
        return render(
            self.request,
            "resources/dashboard.html",
            {"resources": resources, "upload_form": form},
        )

    def _wants_json(self) -> bool:
        return self.request.accepts("application/json")


class ResourceDetailView(TeacherRequiredMixin, DetailView):
    model = Resource
    template_name = "resources/detail.html"
    context_object_name = "resource"

    def get_queryset(self):
        return Resource.objects.prefetch_related("courses", "ingestion_jobs")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        resource: Resource = self.object
        ctx["book_cover_url"] = ""
        ctx["book_cover_lookup_eligible"] = False
        if resource.resource_type == Resource.ResourceType.BOOK:
            ctx["book_cover_lookup_eligible"] = bool(
                normalise_isbn(clean_isbn(resource.isbn or ""))
            )
            ctx["book_cover_url"] = ensure_book_cover_url(resource)
        return ctx


class ResourceEditView(TeacherRequiredMixin, UpdateView):
    model = Resource
    form_class = ResourceEditForm
    template_name = "resources/edit.html"

    def get_queryset(self):
        return Resource.objects.prefetch_related("courses")

    def form_valid(self, form):
        from django.http import HttpResponseRedirect

        before = set(self.object.courses.values_list("id", flat=True))
        old_norm = normalise_isbn(clean_isbn(self.object.isbn or ""))
        new_norm = normalise_isbn(clean_isbn(form.cleaned_data.get("isbn") or ""))
        self.object = form.save(commit=False)
        if old_norm != new_norm:
            self.object.cover_image_url = ""
        self.object.save()
        form.save_m2m()
        after = set(self.object.courses.values_list("id", flat=True))
        if before != after:
            messages.success(
                self.request,
                "Course links saved. Search index metadata was updated in place (no full re-ingestion).",
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("resources:detail", kwargs={"pk": self.object.pk})


class ResourceDeleteView(TeacherRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        resource = get_object_or_404(Resource, pk=pk)
        rid = int(resource.id)
        path = getattr(resource.uploaded_file, "path", None)
        try:
            delete_resource_vectors(rid, resource.vector_collection or None)
        except Exception as exc:
            logger.warning("Chroma delete failed (continuing DB delete): %s", exc)
        try:
            resource.uploaded_file.delete(save=False)
        except Exception as exc:
            logger.warning("File delete failed: %s", exc)
        resource.delete()
        messages.success(request, "Resource deleted.")
        return redirect("resources:dashboard")


class ResourceReingestView(TeacherRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        resource = get_object_or_404(Resource, pk=pk)
        job = ResourceIngestionJob.objects.create(
            resource=resource,
            status=ResourceIngestionJob.Status.QUEUED,
            message="Manual re-ingest",
        )
        try:
            ingest_resource(resource.id, job.id)
            messages.success(request, "Re-ingestion complete.")
        except Exception as exc:
            messages.error(request, f"Re-ingestion failed: {exc}")
        return redirect("resources:detail", pk=resource.pk)


class ResourceMetadataLookupRetryView(TeacherRequiredMixin, View):
    """POST: re-run ISBN metadata lookup from stored `Resource.isbn`."""

    http_method_names = ["post"]

    def post(self, request, pk):
        resource = get_object_or_404(Resource, pk=pk)
        if not (resource.isbn or "").strip():
            messages.error(request, "This resource has no ISBN. Add one under Edit metadata, then retry.")
            return redirect("resources:detail", pk=resource.pk)
        old_norm = normalise_isbn(clean_isbn(resource.isbn or ""))
        apply_metadata_lookup_to_resource(resource)
        resource.save()
        new_norm = normalise_isbn(clean_isbn(resource.isbn or ""))
        if old_norm != new_norm:
            Resource.objects.filter(pk=resource.pk).update(cover_image_url="")
        if resource.metadata_lookup_status == Resource.MetadataLookupStatus.SUCCESS:
            messages.success(request, "Metadata lookup completed successfully.")
        else:
            err = (resource.metadata_lookup_error or "").strip()
            messages.warning(request, err or "Metadata lookup did not find a title.")
        return redirect("resources:detail", pk=resource.pk)


class IngestionJobProgressView(TeacherRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, job_id):
        job = get_object_or_404(ResourceIngestionJob, pk=job_id)
        return JsonResponse(
            {
                "status": job.status,
                "progress_percent": job.progress_percent,
                "completed_steps": job.completed_steps,
                "total_steps": job.total_steps,
                "message": job.message,
                "error_message": job.error_message,
            }
        )


class ResourceRetrievalTestView(TeacherRequiredMixin, View):
    template_name = "resources/test_retrieval.html"

    def get(self, request):
        ctx = {
            "query": request.GET.get("q", ""),
            "top_k": request.GET.get("top_k", "5"),
            "course_id": request.GET.get("course_id", ""),
            "resource_type": request.GET.get("resource_type", ""),
            "resource_id": request.GET.get("resource_id", ""),
            "results": [],
        }
        return self._render(request, ctx)

    def post(self, request):
        query = (request.POST.get("query") or "").strip()
        try:
            top_k = int(request.POST.get("top_k") or 5)
        except ValueError:
            top_k = 5
        top_k = max(1, min(top_k, 50))
        course_id = request.POST.get("course_id") or ""
        resource_type = (request.POST.get("resource_type") or "").strip() or None
        resource_id = request.POST.get("resource_id") or ""
        course_id_int = int(course_id) if course_id.strip().isdigit() else None
        resource_id_int = int(resource_id) if resource_id.strip().isdigit() else None

        hits: list = []
        formatted: list = []
        error = ""
        try:
            if not query:
                raise ValueError("Query is required.")
            hits = query_similar_chunks(
                query,
                top_k=top_k,
                course_id=course_id_int,
                resource_type=resource_type,
                resource_id=resource_id_int,
            )
            formatted = format_api_results(hits, text_preview_chars=800)
            ResourceRetrievalLog.objects.create(
                query=query,
                top_k=top_k,
                results=formatted,
                searched_by=request.user if request.user.is_authenticated else None,
            )
        except Exception as exc:
            error = str(exc)
            logger.exception("Retrieval test failed")

        ctx = {
            "query": query,
            "top_k": str(top_k),
            "course_id": course_id,
            "resource_type": resource_type or "",
            "resource_id": resource_id,
            "results": formatted if not error else [],
            "error": error,
            "raw_hits": hits if not error else [],
        }
        return self._render(request, ctx)

    def _render(self, request, ctx):
        from django.shortcuts import render

        return render(request, self.template_name, ctx)
