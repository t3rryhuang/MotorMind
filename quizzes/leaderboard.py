"""
Leaderboard rankings for a quiz.

Rankings use each user's *best* attempt only (highest correct_answers; ties broken by
faster completion_time_seconds, then earlier created_at).

The leaderboard is derived from ``QuizAttempt`` rows — no separate table. Saving a new
attempt automatically changes computed ranks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.contrib.auth import get_user_model
from django.db import connection

User = get_user_model()


@dataclass(frozen=True)
class LeaderboardRow:
    rank: int
    attempt_id: int
    student_id: int
    username: str
    correct_answers: int
    total_questions: int
    completion_time_seconds: int | None
    completed_at: datetime

    @property
    def score_label(self) -> str:
        return f"{self.correct_answers}/{self.total_questions}"

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


def _row_from_cursor(columns: list[str], row: tuple[Any, ...]) -> LeaderboardRow:
    data = dict(zip(columns, row))
    uname_col = User.USERNAME_FIELD
    return LeaderboardRow(
        rank=int(data["leaderboard_rank"]),
        attempt_id=int(data["attempt_id"]),
        student_id=int(data["student_id"]),
        username=str(data.get(uname_col) or data.get("username", "")),
        correct_answers=int(data["correct_answers"]),
        total_questions=int(data["total_questions"]),
        completion_time_seconds=(
            int(data["completion_time_seconds"])
            if data["completion_time_seconds"] is not None
            else None
        ),
        completed_at=data["created_at"],
    )


def fetch_leaderboard_for_quiz(quiz_id: int) -> list[LeaderboardRow]:
    """
    Return all users' best attempts for this quiz, ordered by rank (SQL above).
    """
    qn = connection.ops.quote_name
    user_table = qn(User._meta.db_table)
    username_field = qn(User.USERNAME_FIELD)

    sql = f"""
        WITH best_per_user AS (
            SELECT
                a.id AS attempt_id,
                a.student_id,
                a.correct_answers,
                a.total_questions,
                a.completion_time_seconds,
                a.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY a.student_id
                    ORDER BY
                        a.correct_answers DESC,
                        a.completion_time_seconds ASC NULLS LAST,
                        a.created_at ASC
                ) AS user_best_rn
            FROM quizzes_quizattempt a
            WHERE a.quiz_id = %s
              AND a.total_questions > 0
        ),
        ranked AS (
            SELECT
                b.attempt_id,
                b.student_id,
                b.correct_answers,
                b.total_questions,
                b.completion_time_seconds,
                b.created_at,
                ROW_NUMBER() OVER (
                    ORDER BY
                        b.correct_answers DESC,
                        b.completion_time_seconds ASC NULLS LAST,
                        b.created_at ASC
                ) AS leaderboard_rank
            FROM best_per_user b
            WHERE b.user_best_rn = 1
        )
        SELECT
            r.leaderboard_rank,
            r.attempt_id,
            r.student_id,
            u.{username_field},
            r.correct_answers,
            r.total_questions,
            r.completion_time_seconds,
            r.created_at
        FROM ranked r
        JOIN {user_table} u ON u.{qn(User._meta.pk.column)} = r.student_id
        ORDER BY r.leaderboard_rank
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [quiz_id])
        columns = [c[0] for c in cursor.description]
        return [_row_from_cursor(columns, row) for row in cursor.fetchall()]


def top_n_for_quiz(quiz_id: int, n: int = 10) -> list[LeaderboardRow]:
    rows = fetch_leaderboard_for_quiz(quiz_id)
    return rows[:n]


def rank_for_user(quiz_id: int, user_id: int) -> LeaderboardRow | None:
    """Return this user's ranked best row, or None if they have no qualifying attempts."""
    for row in fetch_leaderboard_for_quiz(quiz_id):
        if row.student_id == user_id:
            return row
    return None
