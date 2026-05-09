from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from courses.models import Course, TrainingVideo, VideoSection
from quizzes.models import AnswerChoice, Question, Quiz
from quizzes.quiz_editor_save import QuizEditorSaveError, quiz_to_editor_payload, save_quiz_from_payload

User = get_user_model()


class QuizEditorSaveTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="t1", password="pass")
        self.course = Course.objects.create(
            title="C1",
            description="",
            created_by=self.teacher,
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title="Q1",
            description="d",
            pass_mark=70,
        )
        self.video = TrainingVideo.objects.create(
            course=self.course,
            title="V1",
            description="",
            video_url="https://example.com/demo-video",
            transcript="Test transcript for quiz linkage.",
        )
        self.section = VideoSection.objects.create(
            video=self.video,
            title="Intro",
            start_seconds=0,
            end_seconds=60,
            summary="",
            order=0,
        )

    def test_save_roundtrip(self):
        payload = {
            "title": "Updated title",
            "description": "New desc",
            "pass_mark": 80,
            "questions": [
                {
                    "id": None,
                    "question_text": "What is 2+2?",
                    "explanation": "Basic math",
                    "timestamp_seconds": 10,
                    "section_id": self.section.pk,
                    "order": 0,
                    "answers": [
                        {"id": None, "answer_text": "4", "is_correct": True},
                        {"id": None, "answer_text": "5", "is_correct": False},
                    ],
                }
            ],
        }
        save_quiz_from_payload(self.quiz, payload, self.course.pk)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, "Updated title")
        self.assertEqual(self.quiz.pass_mark, 80)
        qs = list(Question.objects.filter(quiz=self.quiz).order_by("order"))
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].section_id, self.section.pk)
        self.assertEqual(qs[0].timestamp_seconds, 10)
        choices = list(qs[0].choices.all())
        self.assertEqual(len(choices), 2)
        self.assertEqual(sum(1 for c in choices if c.is_correct), 1)

    def test_delete_question_not_in_payload(self):
        q = Question.objects.create(
            quiz=self.quiz,
            question_text="Old",
            explanation="",
            order=0,
        )
        AnswerChoice.objects.create(question=q, answer_text="A", is_correct=True)
        payload = {
            "title": "T",
            "description": "",
            "pass_mark": 70,
            "questions": [],
        }
        save_quiz_from_payload(self.quiz, payload, self.course.pk)
        self.assertFalse(Question.objects.filter(pk=q.pk).exists())

    def test_quiz_to_editor_payload_shape(self):
        q = Question.objects.create(
            quiz=self.quiz,
            question_text="Q text",
            explanation="E",
            timestamp_seconds=5,
            section=self.section,
            order=1,
        )
        AnswerChoice.objects.create(question=q, answer_text="Yes", is_correct=True)
        data = quiz_to_editor_payload(self.quiz)
        self.assertEqual(data["title"], self.quiz.title)
        self.assertEqual(len(data["questions"]), 1)
        self.assertEqual(data["questions"][0]["id"], q.pk)
        self.assertEqual(len(data["questions"][0]["answers"]), 1)

    def test_empty_title_raises(self):
        with self.assertRaises(QuizEditorSaveError):
            save_quiz_from_payload(
                self.quiz,
                {"title": "  ", "description": "", "pass_mark": 70, "questions": []},
                self.course.pk,
            )


class CourseQuizEditViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username="te", password="pw")
        from accounts.models import Profile

        profile, _ = Profile.objects.get_or_create(user=self.teacher)
        profile.role = Profile.Role.TEACHER
        profile.save(update_fields=["role"])
        self.course = Course.objects.create(
            title="Course",
            description="",
            created_by=self.teacher,
        )
        self.quiz = Quiz.objects.create(
            course=self.course,
            title="Quiz",
            description="",
            pass_mark=70,
        )

    def test_editor_get_requires_login(self):
        url = f"/admin-panel/courses/{self.course.pk}/quizzes/{self.quiz.pk}/edit/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)

    def test_editor_get_teacher_ok(self):
        self.client.login(username="te", password="pw")
        url = f"/admin-panel/courses/{self.course.pk}/quizzes/{self.quiz.pk}/edit/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Save quiz")
