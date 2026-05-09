import os
from unittest.mock import patch

from django.test import TestCase

from courses.models import Course, TrainingVideo
from courses.utils import extract_youtube_video_id, get_youtube_thumbnail_url


class YouTubeUrlParsingTests(TestCase):
    def test_extract_youtu_be_with_query(self):
        self.assertEqual(
            extract_youtube_video_id(
                "https://youtu.be/n7EGz1Kn3pM?si=lG8GgpVBIG6yyJYp"
            ),
            "n7EGz1Kn3pM",
        )

    def test_extract_watch_url(self):
        self.assertEqual(
            extract_youtube_video_id("https://www.youtube.com/watch?v=n7EGz1Kn3pM"),
            "n7EGz1Kn3pM",
        )

    def test_extract_watch_no_www(self):
        self.assertEqual(
            extract_youtube_video_id("https://youtube.com/watch?v=n7EGz1Kn3pM"),
            "n7EGz1Kn3pM",
        )

    def test_extract_embed(self):
        self.assertEqual(
            extract_youtube_video_id("https://www.youtube.com/embed/n7EGz1Kn3pM"),
            "n7EGz1Kn3pM",
        )

    def test_extract_shorts(self):
        self.assertEqual(
            extract_youtube_video_id("https://www.youtube.com/shorts/n7EGz1Kn3pM"),
            "n7EGz1Kn3pM",
        )

    def test_non_youtube_returns_empty(self):
        self.assertEqual(extract_youtube_video_id("https://example.com/video/abc"), "")

    def test_thumbnail_url_only_for_youtube(self):
        self.assertEqual(
            get_youtube_thumbnail_url("https://youtu.be/n7EGz1Kn3pM?si=x"),
            "https://img.youtube.com/vi/n7EGz1Kn3pM/hqdefault.jpg",
        )
        self.assertEqual(get_youtube_thumbnail_url("https://vimeo.com/123"), "")


class YouTubeAutofillServiceTests(TestCase):
    @patch("courses.services.youtube.get_youtube_transcript")
    @patch("courses.services.youtube.get_youtube_oembed_metadata")
    def test_build_autofill_combines_oembed_and_transcript(self, mock_oembed, mock_tr):
        from courses.services.youtube import build_youtube_autofill_response

        mock_oembed.return_value = {
            "title": "Demo title",
            "author_name": "Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
            "raw_error": "",
        }
        mock_tr.return_value = {
            "transcript": "hello world",
            "segments": [{"start": 0.0, "duration": 1.0, "text": "hello world"}],
            "source": "youtube_captions_manual_en",
            "transcript_source_label": "YouTube captions",
            "error": "",
        }
        out = build_youtube_autofill_response("https://youtu.be/n7EGz1Kn3pM")
        self.assertTrue(out["success"])
        self.assertEqual(out["title"], "Demo title")
        self.assertEqual(out["thumbnail_url"], mock_oembed.return_value["thumbnail_url"])
        self.assertEqual(out["transcript"], "hello world")
        self.assertEqual(out["transcript_source"], "YouTube captions")
        self.assertEqual(out["transcript_source_code"], "youtube_captions_manual_en")
        self.assertEqual(out["warnings"], [])

    @patch("courses.services.youtube.get_youtube_transcript")
    @patch("courses.services.youtube.get_youtube_oembed_metadata")
    def test_build_autofill_warns_when_no_captions(self, mock_oembed, mock_tr):
        from courses.services.youtube import build_youtube_autofill_response

        mock_oembed.return_value = {
            "title": "T",
            "author_name": "",
            "thumbnail_url": "",
            "raw_error": "",
        }
        mock_tr.return_value = {
            "transcript": "",
            "segments": [],
            "source": "",
            "transcript_source_label": "",
            "error": "No YouTube captions available for this video.",
        }
        out = build_youtube_autofill_response("https://youtu.be/n7EGz1Kn3pM")
        self.assertTrue(out["success"])
        self.assertEqual(out["transcript"], "")
        self.assertTrue(any("No captions found" in w for w in out["warnings"]))


class TrainingVideoThumbnailPropertyTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="x")
        self.course = Course.objects.create(
            title="C",
            description="",
            created_by=self.user,
        )

    def test_stored_thumbnail_url_takes_precedence(self):
        v = TrainingVideo.objects.create(
            course=self.course,
            title="T",
            description="",
            video_url="https://www.youtube.com/watch?v=n7EGz1Kn3pM",
            transcript="",
            thumbnail_url="https://i.ytimg.com/vi/custom/hqdefault.jpg",
        )
        self.assertEqual(v.youtube_thumbnail_url, "https://i.ytimg.com/vi/custom/hqdefault.jpg")


class AiDescriptionServiceTests(TestCase):
    def test_missing_key_returns_message(self):
        from courses.services.ai_description import generate_video_description

        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            r = generate_video_description("Title", "yd", "tr")
        self.assertFalse(r["success"])
        self.assertIn("GOOGLE_API_KEY", r["error"])
