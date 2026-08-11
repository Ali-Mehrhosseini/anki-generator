import unittest

from main import (
    WORD_ORIGIN_MARKER,
    apply_card_presentation,
    build_word_origin_html,
)


class WordOriginTests(unittest.TestCase):
    def test_renders_compact_bilingual_word_origin(self):
        data = {
            "word_origin": {
                "breakdown": "compilare + -zione",
                "formation_en": "The suffix -zione forms an action noun.",
                "formation_fa": "پسوند -zione اسمِ عمل می‌سازد.",
                "origin_en": "From Latin compilare.",
                "origin_fa": "از واژهٔ لاتین compilare.",
            },
        }

        rendered = build_word_origin_html(
            data,
            "Both (English + Persian)",
        )

        self.assertIn('class="anki-word-origin"', rendered)
        self.assertIn("compilare + -zione", rendered)
        self.assertIn("forms an action noun", rendered)
        self.assertIn("اسمِ عمل", rendered)
        self.assertIn("From Latin compilare", rendered)
        self.assertIn("minmax(0,1fr)", rendered)
        self.assertIn("overflow-wrap:anywhere", rendered)
        self.assertIn("white-space:normal", rendered)
        self.assertNotIn("white-space:nowrap", rendered)

    def test_omits_section_when_every_origin_field_is_empty(self):
        data = {
            "word_origin": {
                "breakdown": "",
                "formation_en": "",
                "formation_fa": "",
                "origin_en": "",
                "origin_fa": "",
            },
        }

        self.assertEqual(build_word_origin_html(data, "English"), "")

    def test_application_replaces_origin_marker(self):
        data = {
            "word": "compilazione",
            "back_html": f"<div>{WORD_ORIGIN_MARKER}</div>",
            "word_origin": {
                "breakdown": "compilare + -zione",
                "formation_en": "Forms an action noun.",
                "formation_fa": "اسم عمل می‌سازد.",
                "origin_en": "",
                "origin_fa": "",
            },
        }

        result = apply_card_presentation(
            data,
            "Both (English + Persian)",
            {
                "production_card": False,
                "common_phrases": False,
                "smart_grammar": False,
            },
        )

        self.assertNotIn(WORD_ORIGIN_MARKER, result["back_html"])
        self.assertIn('class="anki-word-origin"', result["back_html"])


if __name__ == "__main__":
    unittest.main()
