import json
import unittest
from unittest.mock import patch

from main import (
    build_disambiguation_instruction,
    normalize_interpretation_options,
    process_word,
)


class DisambiguationTests(unittest.TestCase):
    def test_options_are_normalized_deduplicated_and_limited(self):
        options = normalize_interpretation_options([
            {
                "headword": "entro",
                "part_of_speech": "preposition",
                "meaning_en": "by; within",
                "meaning_fa": "تا؛ ظرف",
                "explanation": "Used with deadlines.",
            },
            {
                "headword": "entro",
                "part_of_speech": "preposition",
                "meaning_en": "by; within",
            },
            {
                "headword": "entrare",
                "part_of_speech": "verb",
                "meaning_en": "to enter",
            },
            {
                "headword": "entro",
                "part_of_speech": "unexpected-role",
                "meaning_en": "inside",
            },
            {
                "headword": "extra",
                "part_of_speech": "other",
                "meaning_en": "ignored fourth choice",
            },
        ])

        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]["id"], "meaning-1")
        self.assertEqual(options[1]["headword"], "entrare")
        self.assertEqual(options[2]["part_of_speech"], "other")

    def test_selected_choice_has_highest_priority(self):
        instruction = build_disambiguation_instruction({
            "headword": "entrare",
            "part_of_speech": "verb",
            "meaning_en": "to enter",
            "meaning_fa": "وارد شدن",
            "explanation": "The typed form entro means I enter.",
        })

        self.assertIn("User-selected interpretation — highest priority", instruction)
        self.assertIn("headword `entrare`", instruction)
        self.assertIn("Set `needs_disambiguation` to false", instruction)

    def test_process_pauses_before_audio_when_a_choice_is_required(self):
        generated = {
            "needs_disambiguation": True,
            "interpretations": [
                {
                    "id": "meaning-1",
                    "headword": "entro",
                    "part_of_speech": "preposition",
                    "meaning_en": "by; within",
                    "meaning_fa": "تا؛ ظرف",
                    "explanation": "Used with a deadline.",
                },
                {
                    "id": "meaning-2",
                    "headword": "entrare",
                    "part_of_speech": "verb",
                    "meaning_en": "to enter",
                    "meaning_fa": "وارد شدن",
                    "explanation": "Entro is the first-person form.",
                },
            ],
        }

        with (
            patch("main.generate_content", return_value=generated),
            patch("main.create_polly_client") as create_polly,
        ):
            stream = "".join(process_word(
                "entro",
                "Italian",
                {"gemini": "key", "aws_access": "a", "aws_secret": "s"},
            ))

        self.assertIn('"disambiguation"', stream)
        self.assertIn(json.dumps("entrare"), stream)
        create_polly.assert_not_called()


if __name__ == "__main__":
    unittest.main()
