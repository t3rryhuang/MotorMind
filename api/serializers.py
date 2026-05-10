from rest_framework import serializers

from ar_tasks.models import ARTask, ARTaskStep, StudentARTaskProgress
from courses.models import Course, TrainingVideo, VideoSection
from quizzes.models import AnswerChoice, Question, Quiz


class VideoSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoSection
        fields = (
            "id",
            "title",
            "start_seconds",
            "end_seconds",
            "summary",
            "order",
        )


class TrainingVideoListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingVideo
        fields = (
            "id",
            "title",
            "description",
            "video_url",
            "transcript",
            "transcript_paragraph_starts",
            "thumbnail_url",
            "transcript_source",
            "youtube_description",
            "created_at",
        )


class TrainingVideoDetailSerializer(serializers.ModelSerializer):
    sections = VideoSectionSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingVideo
        fields = (
            "id",
            "title",
            "description",
            "video_url",
            "transcript",
            "transcript_paragraph_starts",
            "thumbnail_url",
            "transcript_source",
            "youtube_description",
            "created_at",
            "sections",
        )


class AnswerChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerChoice
        fields = ("id", "answer_text", "is_correct")


class QuestionSerializer(serializers.ModelSerializer):
    choices = AnswerChoiceSerializer(many=True, read_only=True)
    section = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "question_text",
            "explanation",
            "timestamp_seconds",
            "order",
            "section",
            "choices",
        )


class QuizListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ("id", "title", "description", "pass_mark")


class QuizDetailSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ("id", "title", "description", "pass_mark", "questions")


class ARTaskStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ARTaskStep
        fields = (
            "id",
            "order",
            "instruction",
            "expected_reading",
            "explanation",
            "video_timestamp_seconds",
        )


class ARTaskListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ARTask
        fields = (
            "id",
            "title",
            "description",
            "target_object",
            "scenario_text",
            "expected_action",
            "difficulty",
            "created_at",
            "linked_video_section",
        )


class ARTaskDetailSerializer(serializers.ModelSerializer):
    steps = ARTaskStepSerializer(many=True, read_only=True)
    linked_section = VideoSectionSerializer(
        source="linked_video_section",
        read_only=True,
    )

    class Meta:
        model = ARTask
        fields = (
            "id",
            "title",
            "description",
            "target_object",
            "scenario_text",
            "expected_action",
            "difficulty",
            "created_at",
            "linked_video_section",
            "linked_section",
            "steps",
        )


class CourseListSerializer(serializers.ModelSerializer):
    icon_static_path = serializers.ReadOnlyField()

    class Meta:
        model = Course
        fields = ("id", "title", "description", "icon_name", "icon_static_path", "created_at")


class CourseDetailSerializer(serializers.ModelSerializer):
    videos = TrainingVideoDetailSerializer(many=True, read_only=True)
    quizzes = QuizListSerializer(many=True, read_only=True)
    ar_tasks = ARTaskListSerializer(many=True, read_only=True)
    icon_static_path = serializers.ReadOnlyField()

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "description",
            "icon_name",
            "icon_static_path",
            "created_at",
            "videos",
            "quizzes",
            "ar_tasks",
        )


class StudentARTaskProgressWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentARTaskProgress
        fields = ("status", "notes")

    def save(self, **kwargs):
        request = self.context["request"]
        task = self.context["task"]
        student = request.user
        data = {**self.validated_data, **kwargs}
        obj, _ = StudentARTaskProgress.objects.update_or_create(
            student=student,
            task=task,
            defaults=data,
        )
        self.instance = obj
        return obj


class StudentARTaskProgressReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentARTaskProgress
        fields = ("id", "status", "notes", "updated_at", "task")
