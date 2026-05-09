from django import forms
from django.contrib.auth.forms import AuthenticationForm

from ar_tasks.models import ARTask, ARTaskStep
from courses.models import Course, TrainingVideo, VideoSection
from quizzes.models import AnswerChoice, Question, Quiz


class BootstrapAuthenticationForm(AuthenticationForm):
    """Apply Bootstrap classes to default auth fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ("title", "description")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class TrainingVideoForm(forms.ModelForm):
    class Meta:
        model = TrainingVideo
        fields = (
            "course",
            "video_url",
            "title",
            "description",
            "youtube_description",
            "transcript",
            "thumbnail_url",
            "transcript_source",
        )
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "video_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "transcript": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "thumbnail_url": forms.HiddenInput(),
            "transcript_source": forms.HiddenInput(),
        }
        help_texts = {
            "video_url": "Paste a YouTube URL first, then use Auto-fill for title, thumbnail, and captions.",
            "youtube_description": "Optional. Used for “AI write description”; oEmbed does not include the full YouTube description yet.",
            "transcript": "Filled from YouTube captions when you use Auto-fill (not AI-generated).",
        }


class TrainingVideoEditForm(forms.ModelForm):
    """Edit video metadata without changing owning course (set by URL)."""

    class Meta:
        model = TrainingVideo
        fields = (
            "video_url",
            "title",
            "description",
            "youtube_description",
            "transcript",
            "thumbnail_url",
            "transcript_source",
        )
        widgets = {
            "video_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "transcript": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "thumbnail_url": forms.HiddenInput(),
            "transcript_source": forms.HiddenInput(),
        }
        help_texts = {
            "video_url": "Paste a YouTube URL first, then use Auto-fill for title, thumbnail, and captions.",
            "youtube_description": "Optional. Used for “AI write description”; oEmbed does not include the full YouTube description yet.",
            "transcript": "Filled from YouTube captions when you use Auto-fill (not AI-generated).",
        }


class VideoSectionForm(forms.ModelForm):
    class Meta:
        model = VideoSection
        fields = (
            "video",
            "title",
            "start_seconds",
            "end_seconds",
            "summary",
            "order",
        )
        widgets = {
            "video": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "start_seconds": forms.NumberInput(attrs={"class": "form-control"}),
            "end_seconds": forms.NumberInput(attrs={"class": "form-control"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ("course", "title", "description", "pass_mark")
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "pass_mark": forms.NumberInput(attrs={"class": "form-control"}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = (
            "quiz",
            "section",
            "question_text",
            "explanation",
            "timestamp_seconds",
            "order",
        )
        widgets = {
            "quiz": forms.Select(attrs={"class": "form-select"}),
            "section": forms.Select(attrs={"class": "form-select"}),
            "question_text": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "explanation": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "timestamp_seconds": forms.NumberInput(attrs={"class": "form-control"}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class AnswerChoiceForm(forms.ModelForm):
    class Meta:
        model = AnswerChoice
        fields = ("question", "answer_text", "is_correct")
        widgets = {
            "question": forms.Select(attrs={"class": "form-select"}),
            "answer_text": forms.TextInput(attrs={"class": "form-control"}),
            "is_correct": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ARTaskForm(forms.ModelForm):
    class Meta:
        model = ARTask
        fields = (
            "course",
            "title",
            "description",
            "target_object",
            "scenario_text",
            "expected_action",
            "linked_video_section",
            "difficulty",
        )
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "target_object": forms.Select(attrs={"class": "form-select"}),
            "scenario_text": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "expected_action": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "linked_video_section": forms.Select(attrs={"class": "form-select"}),
            "difficulty": forms.Select(attrs={"class": "form-select"}),
        }


class ARTaskStepForm(forms.ModelForm):
    class Meta:
        model = ARTaskStep
        fields = (
            "task",
            "order",
            "instruction",
            "expected_reading",
            "explanation",
            "video_timestamp_seconds",
        )
        widgets = {
            "task": forms.Select(attrs={"class": "form-select"}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
            "instruction": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "expected_reading": forms.TextInput(attrs={"class": "form-control"}),
            "explanation": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "video_timestamp_seconds": forms.NumberInput(attrs={"class": "form-control"}),
        }
