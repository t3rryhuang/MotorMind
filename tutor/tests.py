from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import Course


@override_settings(GOOGLE_API_KEY="", ELEVENLABS_API_KEY="")
class TutorApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="stu", password="pw")
        self.course = Course.objects.create(
            title="Test course",
            description="Desc",
            created_by=self.user,
        )

    def test_message_requires_login(self):
        url = reverse("courses:course_tutor_message", kwargs={"course_id": self.course.pk})
        r = self.client.post(url, {}, content_type="application/json")
        self.assertEqual(r.status_code, 302)

    def test_message_returns_error_without_gemini(self):
        self.client.login(username="stu", password="pw")
        url = reverse("courses:course_tutor_message", kwargs={"course_id": self.course.pk})
        r = self.client.post(
            url,
            {"message": "Hello", "conversation_id": None, "speak": False},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        data = r.json()
        self.assertFalse(data.get("success"))
        self.assertIn("GOOGLE_API_KEY", data.get("error", ""))
