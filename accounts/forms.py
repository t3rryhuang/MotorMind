from django import forms
from django.contrib.auth.forms import AuthenticationForm

from courses.course_icons import (
    COURSE_ICON_CHOICES,
    COURSE_ICON_SLUGS,
    DEFAULT_COURSE_ICON,
)
from courses.models import Course, TrainingVideo, VideoSection
from quizzes.models import AnswerChoice, Question, Quiz


class BootstrapAuthenticationForm(AuthenticationForm):
    """Apply Bootstrap classes to default auth fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].widget.attrs.setdefault("class", "form-control")


class CourseForm(forms.ModelForm):
    icon_name = forms.ChoiceField(
        label="Course icon",
        choices=COURSE_ICON_CHOICES,
        initial=DEFAULT_COURSE_ICON,
        required=True,
    )

    class Meta:
        model = Course
        fields = ("icon_name", "title", "description")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        raw = (getattr(self.instance, "icon_name", None) or "").strip()
        if raw not in COURSE_ICON_SLUGS:
            self.initial["icon_name"] = DEFAULT_COURSE_ICON

    def clean_icon_name(self):
        val = (self.cleaned_data.get("icon_name") or "").strip()
        if val not in COURSE_ICON_SLUGS:
            return DEFAULT_COURSE_ICON
        return val


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
            "transcript_paragraph_starts",
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
            "transcript_paragraph_starts": forms.HiddenInput(),
            "thumbnail_url": forms.HiddenInput(),
            "transcript_source": forms.HiddenInput(),
        }
        help_texts = {
            "video_url": "Paste a YouTube URL, then use the buttons below for auto-fill, AI title, or AI description.",
            "youtube_description": "Optional. Used for “AI write description”; oEmbed does not include the full YouTube description yet.",
            "transcript": "Filled from YouTube captions when you use Auto-fill; text is reformatted into readable paragraphs (not AI).",
            "transcript_paragraph_starts": "Caption-derived start seconds per paragraph (set automatically with Auto-fill).",
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
            "transcript_paragraph_starts",
            "thumbnail_url",
            "transcript_source",
        )
        widgets = {
            "video_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "transcript": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "transcript_paragraph_starts": forms.HiddenInput(),
            "thumbnail_url": forms.HiddenInput(),
            "transcript_source": forms.HiddenInput(),
        }
        help_texts = {
            "video_url": "Paste a YouTube URL, then use the buttons below for auto-fill, AI title, or AI description.",
            "youtube_description": "Optional. Used for “AI write description”; oEmbed does not include the full YouTube description yet.",
            "transcript": "Filled from YouTube captions when you use Auto-fill; text is reformatted into readable paragraphs (not AI).",
            "transcript_paragraph_starts": "Caption-derived start seconds per paragraph (set automatically with Auto-fill).",
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


