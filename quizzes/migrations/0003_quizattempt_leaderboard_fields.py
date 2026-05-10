# Generated manually for leaderboard feature (ported from Emman branch).

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0002_initial_reading_and_question_refs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="quizattempt",
            name="completion_time_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Seconds from opening the quiz form to submit (server-side).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="quizattempt",
            name="correct_answers",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of questions answered correctly.",
            ),
        ),
        migrations.AddField(
            model_name="quizattempt",
            name="submission_id",
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text="Idempotency token: one DB row per form session.",
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="quizattempt",
            name="total_questions",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Question count for this quiz at submission time.",
            ),
        ),
        migrations.AlterField(
            model_name="quizattempt",
            name="score",
            field=models.IntegerField(
                help_text="Percentage correct (0–100), used for pass/fail.",
            ),
        ),
        migrations.AddIndex(
            model_name="quizattempt",
            index=models.Index(
                fields=["quiz", "student"],
                name="quizzes_qa_quiz_stud_idx",
            ),
        ),
    ]
