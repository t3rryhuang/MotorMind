import uuid

from django import forms


class QuizTakeForm:
    """Factory for a per-quiz ModelForm-style form without a model."""

    @classmethod
    def for_questions(cls, questions):
        """
        Build a form with one radio group per question plus a hidden idempotency UUID.

        The hidden ``_submission_id`` pairs with session state so double POSTs cannot
        create duplicate ``QuizAttempt`` rows.
        """
        fields = {
            "_submission_id": forms.UUIDField(
                widget=forms.HiddenInput(),
                required=True,
            ),
        }
        for q in questions:
            choices = [(str(c.pk), c.answer_text) for c in q.choices.all()]
            fields[f"q_{q.pk}"] = forms.ChoiceField(
                label=q.question_text,
                choices=choices,
                widget=forms.RadioSelect,
                required=True,
            )
        return type("DynamicQuizTakeForm", (forms.Form,), fields)

    @staticmethod
    def new_submission_id() -> uuid.UUID:
        return uuid.uuid4()
