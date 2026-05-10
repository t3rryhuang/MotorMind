from django.contrib import admin

from .models import AnswerChoice, Question, Quiz, QuizAttempt


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    show_change_link = True


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "pass_mark")
    list_filter = ("course",)
    inlines = [QuestionInline]


class AnswerChoiceInline(admin.TabularInline):
    model = AnswerChoice
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text", "quiz", "order")
    list_filter = ("quiz__course",)
    inlines = [AnswerChoiceInline]


@admin.register(AnswerChoice)
class AnswerChoiceAdmin(admin.ModelAdmin):
    list_display = ("answer_text", "question", "is_correct")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "quiz",
        "correct_answers",
        "total_questions",
        "score",
        "completion_time_seconds",
        "passed",
        "created_at",
    )
    list_filter = ("passed", "quiz")
    readonly_fields = ("submission_id",)
