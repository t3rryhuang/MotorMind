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
    score = models.IntegerField()
    passed = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} — {self.quiz} ({self.score}%)"
