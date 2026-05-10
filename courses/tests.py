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

    def test_training_video_youtube_embed_url_property(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        u = User.objects.create_user(username="embedprop", password="x")
        c = Course.objects.create(title="C", description="", created_by=u)
        v = TrainingVideo.objects.create(
            course=c,
            title="V",
            description="",
            video_url="https://youtu.be/n7EGz1Kn3pM?si=abc",
        )
        self.assertEqual(v.youtube_embed_url, "https://www.youtube.com/embed/n7EGz1Kn3pM")
        v2 = TrainingVideo.objects.create(
            course=c,
            title="Other",
            description="",
            video_url="https://example.com/file.mp4",
        )
        self.assertEqual(v2.youtube_embed_url, "")
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
        self.assertIn("transcript_paragraph_starts", out)
        self.assertIsInstance(out["transcript_paragraph_starts"], list)
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


class AiTitleServiceTests(TestCase):
    def test_missing_key_returns_message(self):
        from courses.services.ai_description import generate_educational_title

        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            r = generate_educational_title("Long #hashtag title", transcript="x", youtube_description="y")
        self.assertFalse(r["success"])
        self.assertIn("GOOGLE_API_KEY", r["error"])


class TranscriptFormattingTests(TestCase):
    def test_strips_music_tokens(self):
        from courses.services.transcript_formatting import format_transcript_for_reading

        raw = "[music] Hello there. How are you? >> [Music] Fine thanks."
        out = format_transcript_for_reading(raw)
        self.assertNotIn("[music]", out.lower())
        self.assertIn("Hello there", out)

    def test_format_segments_joins_and_formats(self):
        from courses.services.transcript_formatting import format_transcript_segments

        segs = [
            {"text": "First sentence here."},
            {"text": "Second sentence follows."},
        ]
        out = format_transcript_segments(segs)
        self.assertIn("First sentence", out)
        self.assertIn("Second sentence", out)
        self.assertIn("First sentence here.", out)

    def test_segment_paragraph_starts_align_with_paragraphs(self):
        from courses.services.transcript_formatting import (
            format_transcript_segments,
            format_transcript_segments_with_paragraph_starts,
        )

        segs = [
            {"start": 0.0, "duration": 1.0, "text": "Hi."},
            {"start": 2.0, "duration": 1.0, "text": "Bye."},
        ]
        plain = format_transcript_segments(segs)
        timed, starts = format_transcript_segments_with_paragraph_starts(segs)
        self.assertEqual(plain, timed)
        n_para = len([p for p in plain.split("\n\n") if p.strip()])
        self.assertEqual(len(starts), n_para)

    def test_split_transcript_paragraphs_normalizes_crlf(self):
        from courses.services.transcript_formatting import split_transcript_paragraphs

        text = "First block.\r\n\r\nSecond block."
        paras = split_transcript_paragraphs(text)
        self.assertEqual(len(paras), 2)
        self.assertIn("First", paras[0])
        self.assertIn("Second", paras[1])


class YouTubeAutofillFormattedTranscriptTests(TestCase):
    @patch("courses.services.youtube.get_youtube_transcript")
    @patch("courses.services.youtube.get_youtube_oembed_metadata")
    def test_autofill_formats_segment_transcript(self, mock_oembed, mock_tr):
        from courses.services.youtube import build_youtube_autofill_response

        mock_oembed.return_value = {
            "title": "Demo title",
            "author_name": "Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
            "raw_error": "",
        }
        mock_tr.return_value = {
            "transcript": "",
            "segments": [
                {"start": 0.0, "duration": 1.0, "text": "Hello."},
                {"start": 1.0, "duration": 1.0, "text": "World."},
            ],
            "source": "youtube_captions_manual_en",
            "transcript_source_label": "YouTube captions",
            "error": "",
        }
        out = build_youtube_autofill_response("https://youtu.be/n7EGz1Kn3pM")
        self.assertIn("Hello", out["transcript"])
        self.assertIn("World", out["transcript"])
        self.assertIn("Hello.", out["transcript"])


class VideoSectionsSuggestionsTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="secfill", password="x")
        self.course = Course.objects.create(
            title="Course",
            description="",
            created_by=self.user,
        )

    def test_fallback_merges_many_paragraphs_capped(self):
        from courses.services.section_suggestions import suggest_sections_fallback

        n = 88
        paras = [f"Paragraph {i} body." for i in range(n)]
        starts = [i * 25 for i in range(n)]
        secs = suggest_sections_fallback(paras, starts, title="T", duration_seconds=7200)
        self.assertLessEqual(len(secs), 12)
        self.assertGreaterEqual(len(secs), 3)

    @patch("courses.services.section_suggestions.suggest_sections_with_ai")
    def test_build_and_apply_with_crlf_transcript(self, mock_ai):
        mock_ai.return_value = {"success": False, "sections": [], "error": "skip ai"}
        from courses.services.section_suggestions import (
            apply_suggested_sections,
            build_section_suggestions,
        )

        v = TrainingVideo.objects.create(
            course=self.course,
            title="V",
            description="",
            video_url="",
            transcript="",
            transcript_paragraph_starts=[],
        )
        text = "Para one.\r\n\r\nPara two."
        starts = [5, 100]
        out = build_section_suggestions(
            title="T",
            video_url="",
            transcript=text,
            paragraph_starts=starts,
        )
        self.assertTrue(out["success"])
        self.assertLessEqual(len(out["sections"]), 12)
        n, err = apply_suggested_sections(v, out["sections"], replace=True)
        self.assertIsNone(err)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(v.sections.count(), n)

    def test_append_idempotent_when_all_rows_duplicate(self):
        from courses.models import VideoSection
        from courses.services.section_suggestions import apply_suggested_sections

        v = TrainingVideo.objects.create(
            course=self.course,
            title="V",
            description="",
            video_url="",
            transcript="",
            transcript_paragraph_starts=[],
        )
        VideoSection.objects.create(
            video=v,
            title="Part A",
            start_seconds=10,
            end_seconds=50,
            summary="",
            order=0,
        )
        rows = [{"title": "Part A", "start_seconds": 10, "end_seconds": 50, "summary": ""}]
        n, err = apply_suggested_sections(v, rows, replace=False)
        self.assertEqual(n, 0)
        self.assertIsNone(err)
        self.assertEqual(v.sections.count(), 1)


class CourseIconStaticPathTests(TestCase):
    def test_valid_slug_path(self):
        from django.contrib.auth import get_user_model

        u = get_user_model().objects.create_user(username="ic", password="x")
        c = Course.objects.create(
            title="T", description="", created_by=u, icon_name="fuse"
        )
        self.assertEqual(c.icon_static_path, "images/course-icons/fuse.svg")

    def test_invalid_slug_falls_back_to_default(self):
        from django.contrib.auth import get_user_model

        u = get_user_model().objects.create_user(username="ic2", password="x")
        c = Course.objects.create(
            title="T2", description="", created_by=u, icon_name="not-a-real-icon"
        )
        self.assertEqual(c.icon_static_path, "images/course-icons/default.svg")
