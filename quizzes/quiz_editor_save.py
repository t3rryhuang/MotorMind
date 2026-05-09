"""
Bulk save for the teacher quiz editor (JSON payload, one POST).
"""

from django.db import transaction

from courses.models import VideoSection

from .models import AnswerChoice, Question, Quiz


class QuizEditorSaveError(ValueError):
    pass


def _coerce_int(val, default=None, *, minimum=None, maximum=None):
    if val is None or val == "":
        return default
    try:
        n = int(val)
    except (TypeError, ValueError) as exc:
        raise QuizEditorSaveError("Invalid number in payload.") from exc
    if minimum is not None and n < minimum:
        raise QuizEditorSaveError("Value out of range.")
    if maximum is not None and n > maximum:
        raise QuizEditorSaveError("Value out of range.")
    return n


def _resolve_section(course_id, section_id):
    if section_id is None or section_id == "":
        return None
    sid = _coerce_int(section_id, minimum=1)
    sec = VideoSection.objects.filter(pk=sid, video__course_id=course_id).first()
    if not sec:
        return None
    return sec


@transaction.atomic
def save_quiz_from_payload(quiz: Quiz, payload: dict, course_id: int) -> None:
    """
    Replace quiz metadata and full question / answer tree from payload.

    Questions and choices not present in the payload are deleted.
    """
    if not isinstance(payload, dict):
        raise QuizEditorSaveError("Invalid payload.")

    title = (payload.get("title") or "").strip()
    if not title:
        raise QuizEditorSaveError("Quiz title is required.")

    description = (payload.get("description") or "").strip()
    pass_mark = _coerce_int(payload.get("pass_mark"), default=70, minimum=0, maximum=100)

    quiz.title = title[:255]
    quiz.description = description
    quiz.pass_mark = pass_mark
    quiz.save(update_fields=["title", "description", "pass_mark"])

    questions_in = payload.get("questions")
    if questions_in is None:
        questions_in = []
    if not isinstance(questions_in, list):
        raise QuizEditorSaveError("questions must be a list.")

    kept_question_pks = []

    for order_idx, qd in enumerate(questions_in):
        if not isinstance(qd, dict):
            continue
        qtext = (qd.get("question_text") or "").strip()
        if not qtext:
            continue

        qid = qd.get("id")
        q_obj = None
        if isinstance(qid, int) and qid > 0:
            q_obj = Question.objects.filter(pk=qid, quiz_id=quiz.pk).first()

        if q_obj is None:
            q_obj = Question(quiz=quiz)

        section = _resolve_section(course_id, qd.get("section_id"))
        ts_raw = qd.get("timestamp_seconds")
        if ts_raw is None or ts_raw == "":
            ts_val = None
        else:
            ts_val = _coerce_int(ts_raw, minimum=0)

        q_obj.question_text = qtext
        q_obj.explanation = (qd.get("explanation") or "").strip()
        q_obj.timestamp_seconds = ts_val
        q_obj.section = section
        q_obj.order = _coerce_int(qd.get("order"), default=order_idx, minimum=0)
        q_obj.save()
        kept_question_pks.append(q_obj.pk)

        answers_in = qd.get("answers")
        if answers_in is None:
            answers_in = []
        if not isinstance(answers_in, list):
            raise QuizEditorSaveError("answers must be a list.")

        kept_choice_pks = []
        for cd in answers_in:
            if not isinstance(cd, dict):
                continue
            atext = (cd.get("answer_text") or "").strip()
            if not atext:
                continue

            cid = cd.get("id")
            c_obj = None
            if isinstance(cid, int) and cid > 0:
                c_obj = AnswerChoice.objects.filter(pk=cid, question_id=q_obj.pk).first()

            if c_obj is None:
                c_obj = AnswerChoice(question=q_obj)

            c_obj.answer_text = atext[:500]
            c_obj.is_correct = bool(cd.get("is_correct"))
            c_obj.save()
            kept_choice_pks.append(c_obj.pk)

        AnswerChoice.objects.filter(question=q_obj).exclude(pk__in=kept_choice_pks).delete()

    Question.objects.filter(quiz=quiz).exclude(pk__in=kept_question_pks).delete()


def quiz_to_editor_payload(quiz: Quiz) -> dict:
    """Serialize quiz for the editor JSON script tag."""
    questions = []
    for q in quiz.questions.order_by("order", "pk").prefetch_related("choices"):
        questions.append(
            {
                "id": q.pk,
                "question_text": q.question_text,
                "explanation": q.explanation or "",
                "timestamp_seconds": q.timestamp_seconds,
                "section_id": q.section_id,
                "order": q.order,
                "answers": [
                    {
                        "id": c.pk,
                        "answer_text": c.answer_text,
                        "is_correct": c.is_correct,
                    }
                    for c in q.choices.all()
                ],
            }
        )
    return {
        "title": quiz.title,
        "description": quiz.description or "",
        "pass_mark": quiz.pass_mark,
        "questions": questions,
    }
