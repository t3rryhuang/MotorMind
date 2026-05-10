from django.urls import path

from . import views

app_name = "quizzes"

urlpatterns = [
    path(
        "quizzes/<int:quiz_id>/take/",
        views.QuizTakeView.as_view(),
        name="quiz_take",
    ),
    path(
        "quizzes/<int:quiz_id>/result/",
        views.QuizResultView.as_view(),
        name="quiz_result",
    ),
    path(
        "quizzes/<int:quiz_id>/leaderboard/",
        views.QuizLeaderboardView.as_view(),
        name="quiz_leaderboard",
    ),
]
