from django.conf import settings
from django.db import models


class Quiz(models.Model):
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="quizzes",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    pass_mark = models.IntegerField(default=70)

    class Meta:
        ordering = ["pk"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    section = models.ForeignKey(
        "courses.VideoSection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    question_text = models.TextField()
    explanation = models.TextField(blank=True)
    timestamp_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional jump-back point in the training video (seconds).",
    )
    order = models.PositiveIntegerField(default=0)
    source_refs = models.JSONField(
        default=list,
        blank=True,
        help_text="Citation ids from reading context (e.g. B1, V1) for AI-assisted questions.",
    )

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.question_text[:80]


class AnswerChoice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
    )
    answer_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.answer_text[:60]


class QuizAttempt(models.Model):
    """One submitted quiz run. Leaderboard uses each user's best attempt (see quizzes.leaderboard)."""

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    score = models.IntegerField(
        help_text="Percentage correct (0–100), used for pass/fail.",
    )
    passed = models.BooleanField()
    correct_answers = models.PositiveIntegerField(
        default=0,
        help_text="Number of questions answered correctly.",
    )
    total_questions = models.PositiveIntegerField(
        default=0,
        help_text="Question count for this quiz at submission time.",
    )
    completion_time_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Seconds from opening the quiz form to submit (server-side).",
    )
    submission_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
        help_text="Idempotency token: one DB row per form session.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["quiz", "student"],
                name="quizzes_qa_quiz_stud_idx",
            ),
        ]

    def __str__(self):
        return f"{self.student} — {self.quiz} ({self.score}%)"

    @property
    def score_fraction_label(self) -> str:
        """Human-readable score, e.g. 8/10."""
        if self.total_questions:
            return f"{self.correct_answers}/{self.total_questions}"
        return f"{self.score}%"

    @property
    def time_display(self) -> str:
        if self.completion_time_seconds is None:
            return "—"
        s = self.completion_time_seconds
        if s < 60:
            return f"{s}s"
        m, sec = divmod(s, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}h {m}m {sec}s"
        return f"{m}m {sec}s"
