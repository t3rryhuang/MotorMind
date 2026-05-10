from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import DetailView, FormView, TemplateView

from .forms import QuizTakeForm
from .leaderboard import rank_for_user, top_n_for_quiz
from .models import AnswerChoice, Question, Quiz, QuizAttempt


def _quiz_session_keys(quiz_pk: int) -> tuple[str, str]:
    return (
        f"quiz_take_{quiz_pk}_submission",
        f"quiz_take_{quiz_pk}_started_at",
    )


class QuizTakeView(LoginRequiredMixin, FormView):
    """Show quiz questions; on POST, record one attempt per session (idempotent)."""

    template_name = "quizzes/quiz_take.html"

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(
            Quiz.objects.select_related("course"),
            pk=kwargs["quiz_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        sub_key, start_key = _quiz_session_keys(self.quiz.pk)
        if sub_key not in request.session:
            request.session[sub_key] = str(QuizTakeForm.new_submission_id())
            request.session[start_key] = timezone.now().isoformat()
            request.session.modified = True
        return super().get(request, *args, **kwargs)

    def get_form_class(self):
        questions = list(
            Question.objects.filter(quiz=self.quiz)
            .prefetch_related("choices")
            .order_by("order", "pk")
        )
        return QuizTakeForm.for_questions(questions)

    def get_initial(self):
        sub_key, _ = _quiz_session_keys(self.quiz.pk)
        sid = self.request.session.get(sub_key)
        initial = {}
        if sid:
            initial["_submission_id"] = sid
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["quiz"] = self.quiz
        ctx["questions"] = (
            Question.objects.filter(quiz=self.quiz)
            .prefetch_related("choices")
            .order_by("order", "pk")
        )
        return ctx

    def form_valid(self, form):
        sub_key, start_key = _quiz_session_keys(self.quiz.pk)
        submitted = form.cleaned_data.get("_submission_id")
        expected = self.request.session.get(sub_key)
        if not expected or str(submitted) != str(expected):
            messages.error(
                self.request,
                "This quiz session is invalid or was already submitted. Please start again.",
            )
            return redirect("quizzes:quiz_take", quiz_id=self.quiz.pk)

        questions = list(
            Question.objects.filter(quiz=self.quiz)
            .prefetch_related("choices")
            .order_by("order", "pk")
        )
        total = len(questions)
        if total == 0:
            messages.warning(self.request, "This quiz has no questions yet.")
            return redirect("courses:course_detail", pk=self.quiz.course_id)

        correct = 0
        for q in questions:
            field = f"q_{q.pk}"
            selected_id = form.cleaned_data.get(field)
            if not selected_id:
                continue
            choice = AnswerChoice.objects.filter(pk=selected_id, question=q).first()
            if choice and choice.is_correct:
                correct += 1

        score = int(round(100 * correct / total))
        passed = score >= self.quiz.pass_mark

        started_raw = self.request.session.get(start_key)
        started = parse_datetime(started_raw) if started_raw else None
        completed = timezone.now()
        if started:
            elapsed = max(0, int((completed - started).total_seconds()))
        else:
            elapsed = None

        try:
            with transaction.atomic():
                QuizAttempt.objects.create(
                    quiz=self.quiz,
                    student=self.request.user,
                    score=score,
                    passed=passed,
                    correct_answers=correct,
                    total_questions=total,
                    completion_time_seconds=elapsed,
                    submission_id=submitted,
                )
        except IntegrityError:
            # Duplicate POST with the same submission_id (race) — treat as success.
            messages.info(
                self.request,
                "Your answers were already recorded.",
            )
            return redirect("quizzes:quiz_result", quiz_id=self.quiz.pk)

        if sub_key in self.request.session:
            del self.request.session[sub_key]
        if start_key in self.request.session:
            del self.request.session[start_key]
        self.request.session.modified = True

        messages.success(
            self.request,
            "Quiz submitted — see your result on the next page.",
        )
        return redirect("quizzes:quiz_result", quiz_id=self.quiz.pk)


class QuizResultView(LoginRequiredMixin, DetailView):
    model = Quiz
    template_name = "quizzes/quiz_result.html"
    context_object_name = "quiz"
    pk_url_kwarg = "quiz_id"

    def get_queryset(self):
        return Quiz.objects.select_related("course")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        attempt = (
            QuizAttempt.objects.filter(quiz=self.object, student=self.request.user)
            .order_by("-created_at")
            .first()
        )
        ctx["last_attempt"] = attempt
        ctx["score"] = attempt.score if attempt else None
        ctx["passed"] = attempt.passed if attempt else None
        ctx["user_rank"] = rank_for_user(self.object.pk, self.request.user.pk)
        return ctx


class QuizLeaderboardView(LoginRequiredMixin, TemplateView):
    """Top 10 best attempts (per user) for a quiz, plus current user's rank."""

    template_name = "quizzes/quiz_leaderboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        quiz = get_object_or_404(
            Quiz.objects.select_related("course"),
            pk=self.kwargs["quiz_id"],
        )
        ctx["quiz"] = quiz
        ctx["top_10"] = top_n_for_quiz(quiz.pk, 10)
        ctx["user_rank"] = rank_for_user(quiz.pk, self.request.user.pk)
        return ctx
