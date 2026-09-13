import unittest

from main import FrontCardValidationError, validate_recognition_front


class FrontValidationTests(unittest.TestCase):
    def test_accepts_canonical_lemma_with_one_stressed_vowel(self):
        data = {
            "word": "godersi",
            "front_html": (
                "<div>god<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">e</span>rsi</div>"
            ),
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)

    def test_accepts_noun_article_around_bare_word_field(self):
        data = {
            "word": "amico",
            "front_html": (
                "<div>l’am<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">i</span>co</div>"
            ),
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)

    def test_repairs_artificial_accent_inside_stress_marker(self):
        data = {
            "word": "molestatore",
            "front_html": (
                "<div>il molestat<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">ó</span>re</div>"
            ),
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertIn(">o</span>re", data["front_html"])
        self.assertNotIn("ó", data["front_html"])

    def test_repairs_combined_ancora_pronunciation_decoration(self):
        for before, marked, after, hint in [
            ("an-", "cò", "-ra", "an-CO-ra"),
            ("an-", "ò", "", "an-O"),
            ("an-c", "ò", "-ra", "an-CO-ra"),
            ("", "àn", "-co-ra", "AN-co-ra"),
            ("an", "cò", "ra", "an-CO-ra"),
        ]:
            with self.subTest(marked=marked, before=before, after=after):
                data = {
                    "word": "ancora",
                    "front_html": (
                        f'<div>{before}<span style="border-bottom:2px dotted '
                        f'currentColor;padding-bottom:2px;">{marked}</span>{after}</div>'
                    ),
                    "back_html": f"<div>Stress: {hint}</div>",
                }
                if not after:
                    original = data["front_html"]
                    with self.assertRaises(FrontCardValidationError):
                        validate_recognition_front(data, "Italian")
                    self.assertEqual(data["front_html"], original)
                else:
                    self.assertIs(validate_recognition_front(data, "Italian"), data)
                    self.assertNotIn("ò", data["front_html"])
                    self.assertNotIn("à", data["front_html"])
                    self.assertRegex(data["front_html"], r'>[ao]</span>')

    def test_repairs_live_ancora_response_with_missing_consonant(self):
        data = {
            "word": "ancora", "tts_word": "ancora",
            "front_html": '<div>an<span style="border-bottom:2px dotted currentColor;">o</span>ra</div>',
            "back_html": "<div>Stress: an-CO-ra</div><div>Voglio ancora un caffè.</div>",
        }
        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertEqual(data["front_html"], '<div>anc<span style="border-bottom:2px dotted currentColor;">o</span>ra</div>')

    def test_missing_consonant_repair_requires_agreement(self):
        for changes in [
            {"tts_word": "anora"}, {"tts_word": ""},
            {"back_html": "Stress: AN-co-ra"},
            {"back_html": "Stress: an-O-ra"},
            {"back_html": ""},
            {"front_html": '<div>a<span style="border-bottom:2px dotted currentColor;">o</span>ra</div>'},
        ]:
            with self.subTest(changes=changes):
                data = {
                    "word": "ancora", "tts_word": "ancora",
                    "front_html": '<div>an<span style="border-bottom:2px dotted currentColor;">o</span>ra</div>',
                    "back_html": "Stress: an-CO-ra",
                    **changes,
                }
                original = data["front_html"]
                with self.assertRaises(FrontCardValidationError):
                    validate_recognition_front(data, "Italian")
                self.assertEqual(data["front_html"], original)

    def test_does_not_repair_real_accent_in_canonical_word(self):
        data = {
            "word": "città",
            "front_html": (
                "<div>la citt<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">à</span></div>"
            ),
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertIn("à", data["front_html"])

    def test_repairs_consonant_marker_when_back_hint_confirms_previous_vowel(self):
        data = {
            "word": "distruggere",
            "front_html": (
                "<div>distru<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">g</span>gere</div>"
            ),
            "back_html": (
                "<div>verb · transitive</div>"
                "<div>Stress: di-STRUGR-ge-re</div>"
            ),
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertIn(
            "distr<span style=\"border-bottom:2px dotted "
            "currentColor;padding-bottom:2px;\">u</span>ggere",
            data["front_html"],
        )

    def test_shrinks_stressed_syllable_to_back_confirmed_vowel(self):
        data = {
            "word": "distruggere",
            "front_html": (
                "<div>di<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">stru</span>ggere</div>"
            ),
            "back_html": "<div>Stress: di-STRU-gge-re</div>",
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertIn(
            "distr<span style=\"border-bottom:2px dotted "
            "currentColor;padding-bottom:2px;\">u</span>ggere",
            data["front_html"],
        )

    def test_does_not_shrink_ambiguous_multi_vowel_span(self):
        data = {
            "word": "paese",
            "front_html": (
                "<div><span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">pae</span>se</div>"
            ),
            "back_html": "<div>Stress: pa-E-se</div>",
        }

        with self.assertRaisesRegex(
            FrontCardValidationError,
            "other than one vowel",
        ):
            validate_recognition_front(data, "Italian")

    def test_does_not_shift_consonant_marker_when_back_hint_disagrees(self):
        data = {
            "word": "godersi",
            "front_html": (
                "<div>go<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">d</span>ersi</div>"
            ),
            "back_html": "<div>Stress: go-DER-si</div>",
        }

        with self.assertRaisesRegex(
            FrontCardValidationError,
            "other than one vowel",
        ):
            validate_recognition_front(data, "Italian")

    def test_rejects_inflected_syllabified_front_instead_of_lemma(self):
        data = {
            "word": "godersi",
            "front_html": (
                "<div>go<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">d</span>i-ti</div>"
            ),
        }

        with self.assertRaisesRegex(
            FrontCardValidationError,
            "changed or syllabified",
        ):
            validate_recognition_front(data, "Italian")

    def test_repairs_canonical_lemma_split_by_stress_guide_hyphens(self):
        data = {
            "word": "distruggere",
            "front_html": (
                "<div>di-stru<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">g</span>-gere</div>"
            ),
            "back_html": "<div>Stress: di-STRU-gge-re</div>",
        }

        self.assertIs(validate_recognition_front(data, "Italian"), data)
        self.assertNotIn("di-stru", data["front_html"])
        self.assertNotIn("</span>-gere", data["front_html"])
        self.assertIn(
            "distr<span style=\"border-bottom:2px dotted "
            "currentColor;padding-bottom:2px;\">u</span>ggere",
            data["front_html"],
        )

    def test_does_not_replace_an_inflected_front_with_the_lemma(self):
        data = {
            "word": "distruggere",
            "front_html": (
                "<div>distru<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">t</span>ta</div>"
            ),
            "back_html": "<div>Stress: di-STRU-gge-re</div>",
        }

        with self.assertRaisesRegex(
            FrontCardValidationError,
            "changed or syllabified",
        ):
            validate_recognition_front(data, "Italian")

    def test_rejects_stress_span_around_consonant(self):
        data = {
            "word": "godersi",
            "front_html": (
                "<div>go<span style=\"border-bottom:2px dotted "
                "currentColor;padding-bottom:2px;\">d</span>ersi</div>"
            ),
        }

        with self.assertRaisesRegex(
            FrontCardValidationError,
            "other than one vowel",
        ):
            validate_recognition_front(data, "Italian")


if __name__ == "__main__":
    unittest.main()
