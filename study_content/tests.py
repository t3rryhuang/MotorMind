from django.test import SimpleTestCase

from study_content.citation_format import author_surname, chunk_hover_title


class CitationFormatTests(SimpleTestCase):
    def test_author_surname_natural_order(self):
        self.assertEqual(author_surname("Tom Denton"), "Denton")

    def test_author_surname_comma(self):
        self.assertEqual(author_surname("Denton, Tom"), "Denton")

    def test_chunk_hover_includes_section_and_page(self):
        class Fake:
            metadata = {"section_title": "Fuses and relays"}
            source_title = "Auto Systems"
            resource_title = ""
            author = "Tom Denton"
            page_number = 112

        tip = chunk_hover_title(Fake())
        self.assertIn("Auto Systems", tip)
        self.assertIn("Fuses", tip)
        self.assertIn("112", tip)
