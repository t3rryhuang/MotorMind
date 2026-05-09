from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from resources.models import Resource
from resources.services.book_cover import ensure_book_cover_url, openlibrary_cover_url
from resources.services.book_metadata import lookup_book_metadata_by_isbn
from resources.services.resource_upload import build_resource_from_minimal_upload


def _json_response(payload: dict, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


class OpenLibraryWorkAuthorsTests(SimpleTestCase):
    """Edition JSON often omits authors; they appear on the linked work."""

    @patch("resources.services.book_metadata.requests.get")
    def test_resolves_authors_via_work_and_author_endpoints(self, mock_get):
        edition = {
            "title": "Automobile Mechanical And Electrical Systems",
            "publishers": ["Routledge", "Butterworth-Heinemann"],
            "publish_date": "2011",
            "number_of_pages": 528,
            "works": [{"key": "/works/OL17411461W"}],
            "authors": [],
        }
        work = {
            "title": "Automobile Mechanical And Electrical Systems",
            "authors": [{"author": {"key": "/authors/OL36045A"}}],
        }
        author = {"name": "Tom Denton"}

        def side_effect(url, **kwargs):
            self.assertIn("timeout", kwargs)
            if url.endswith("/isbn/9780080969459.json"):
                return _json_response(edition)
            if "/works/OL17411461W.json" in url:
                return _json_response(work)
            if "/authors/OL36045A.json" in url:
                return _json_response(author)
            if "googleapis.com" in url:
                return _json_response({"items": []})
            return _json_response({}, 404)

        mock_get.side_effect = side_effect
        meta = lookup_book_metadata_by_isbn("9780080969459")
        self.assertIn("Automobile", meta["title"])
        self.assertEqual(meta["metadata_source"], "open_library")
        self.assertIn("Tom Denton", meta["author"])
        self.assertEqual(meta["number_of_pages"], 528)
        self.assertEqual(meta["error"], "")

    @patch("resources.services.book_metadata.requests.get")
    def test_google_books_fallback_when_open_library_empty(self, mock_get):
        gb_volume = {
            "items": [
                {
                    "volumeInfo": {
                        "title": "Fallback Title",
                        "authors": ["Someone"],
                        "publisher": "PubCo",
                        "publishedDate": "2020-01-02",
                        "pageCount": 100,
                    }
                }
            ]
        }

        def side_effect(url, **kwargs):
            if "openlibrary.org/isbn" in url:
                return _json_response({}, 404)
            if "googleapis.com" in url:
                return _json_response(gb_volume)
            return _json_response({}, 404)

        mock_get.side_effect = side_effect
        meta = lookup_book_metadata_by_isbn("9780415725774")
        self.assertEqual(meta["title"], "Fallback Title")
        self.assertEqual(meta["metadata_source"], "google_books")
        self.assertEqual(meta["author"], "Someone")


class BuildResourceMetadataTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tmeta", password="x")

    @patch("resources.services.resource_upload.lookup_book_metadata_by_isbn")
    def test_book_upload_success_when_title_only(self, mock_lookup):
        mock_lookup.return_value = {
            "isbn": "9780415725774",
            "title": "Some Book",
            "source_title": "Some Book",
            "authors": [],
            "author": "",
            "publisher": "",
            "year": "2015",
            "description": "",
            "edition": "",
            "number_of_pages": 200,
            "metadata_source": "open_library",
            "raw": {},
            "error": "",
        }
        f = MagicMock()
        f.name = "9780415725774.pdf"
        r = build_resource_from_minimal_upload(
            uploaded_file=f,
            original_filename="9780415725774.pdf",
            explicit_resource_type=Resource.ResourceType.BOOK,
            user=self.user,
        )
        self.assertEqual(r.title, "Some Book")
        self.assertEqual(r.metadata_lookup_status, Resource.MetadataLookupStatus.SUCCESS)
        self.assertEqual(r.number_of_pages, 200)

    @patch("resources.services.resource_upload.lookup_book_metadata_by_isbn")
    def test_book_upload_failed_sets_error_and_isbn_title(self, mock_lookup):
        mock_lookup.return_value = {
            "isbn": "9780415725774",
            "title": "",
            "source_title": "",
            "authors": [],
            "author": "",
            "publisher": "",
            "year": "",
            "description": "",
            "edition": "",
            "number_of_pages": None,
            "metadata_source": "none",
            "raw": {},
            "error": "No title found from Open Library or Google Books.",
        }
        f = MagicMock()
        f.name = "9780415725774.pdf"
        r = build_resource_from_minimal_upload(
            uploaded_file=f,
            original_filename="9780415725774.pdf",
            explicit_resource_type=Resource.ResourceType.BOOK,
            user=self.user,
        )
        self.assertEqual(r.title, "9780415725774")
        self.assertEqual(r.metadata_lookup_status, Resource.MetadataLookupStatus.FAILED)
        self.assertIn("No title", r.metadata_lookup_error)

    def test_invalid_isbn_raises(self):
        f = MagicMock()
        f.name = "9780415725773.pdf"  # wrong check digit (valid length / shape only)
        with self.assertRaises(ValidationError):
            build_resource_from_minimal_upload(
                uploaded_file=f,
                original_filename="9780415725773.pdf",
                explicit_resource_type=Resource.ResourceType.BOOK,
                user=self.user,
            )


class BookCoverTests(TestCase):
    def setUp(self):
        cache.clear()
        self.resource = Resource.objects.create(
            title="Test Book",
            resource_type=Resource.ResourceType.BOOK,
            uploaded_file=SimpleUploadedFile("book.pdf", b"%PDF-1.4"),
            isbn="9780080969459",
        )

    def tearDown(self):
        cache.clear()

    def test_returns_stored_url_without_http(self):
        url = "https://covers.openlibrary.org/b/isbn/9780080969459-L.jpg"
        Resource.objects.filter(pk=self.resource.pk).update(cover_image_url=url)
        self.resource.refresh_from_db()
        with patch("resources.services.book_cover.requests.head") as mock_head:
            out = ensure_book_cover_url(self.resource)
        self.assertEqual(out, url)
        mock_head.assert_not_called()

    @patch("resources.services.book_cover.requests.head")
    def test_probe_success_persists_and_caches(self, mock_head):
        r = MagicMock()
        r.status_code = 200
        r.headers = {"content-type": "image/jpeg"}
        mock_head.return_value = r

        out = ensure_book_cover_url(self.resource)
        expected = openlibrary_cover_url("9780080969459")
        self.assertEqual(out, expected)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.cover_image_url, expected)
        mock_head.assert_called_once()

        mock_head.reset_mock()
        self.resource.cover_image_url = ""
        self.resource.save(update_fields=["cover_image_url"])
        out2 = ensure_book_cover_url(self.resource)
        self.assertEqual(out2, expected)
        mock_head.assert_not_called()

    @patch("resources.services.book_cover.requests.head")
    def test_probe_miss_caches_negative(self, mock_head):
        r = MagicMock()
        r.status_code = 404
        r.headers = {"content-type": "text/html"}
        mock_head.return_value = r

        out = ensure_book_cover_url(self.resource)
        self.assertEqual(out, "")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.cover_image_url, "")

        mock_head.reset_mock()
        out2 = ensure_book_cover_url(self.resource)
        self.assertEqual(out2, "")
        mock_head.assert_not_called()

    def test_empty_isbn_returns_empty(self):
        Resource.objects.filter(pk=self.resource.pk).update(isbn="")
        self.resource.refresh_from_db()
        self.assertEqual(ensure_book_cover_url(self.resource), "")
