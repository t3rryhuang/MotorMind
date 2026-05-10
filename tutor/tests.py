from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from courses.models import Course

from tutor.services.speech_cleanup import clean_text_for_speech


class CleanTextForSpeechTests(SimpleTestCase):
    def test_removes_bracket_refs_and_video_sentence(self):
        raw = (
            "That's why he checked Fuse 11 first [V2]. The resistance reading of 16 ohms "
            "suggested a semi-short to earth [B3]. You can see this around 04:18 in the video."
        )
        spoken = clean_text_for_speech(raw)
        self.assertNotIn("[V2]", spoken)
        self.assertNotIn("[B3]", spoken)
        self.assertNotIn("04:18", spoken)
        self.assertNotIn("You can see", spoken)
        self.assertIn("Fuse 11 first", spoken)
        self.assertIn("semi-short to earth", spoken)

    def test_acceptance_example(self):
        raw = (
            "The technician suspected Fuse 11 because it powered multiple systems [V2]. "
            "This is discussed around 04:18 in the video."
        )
        spoken = clean_text_for_speech(raw)
        self.assertEqual(
            spoken,
            "The technician suspected Fuse 11 because it powered multiple systems",
        )

    def test_book_and_source_parens_removed(self):
        raw = "Check the diagram (Book p.42) and (Source: RMS Diagnostics) for details."
        spoken = clean_text_for_speech(raw)
        self.assertNotIn("Book", spoken)
        self.assertNotIn("Source", spoken)
        self.assertIn("Check the diagram", spoken)

    def test_spoken_abbrev_ecu(self):
        self.assertIn("E C U", clean_text_for_speech("The ECU may log a fault."))


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
