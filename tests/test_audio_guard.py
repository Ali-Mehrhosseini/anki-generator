import unittest

from main import (
    ENGLISH_MEANING_AUDIO_MARKER,
    MAIN_MEANING_END,
    MAIN_MEANING_START,
    _extract_visible_english_meaning,
    _sync_english_meaning_audio_text,
    apply_versioned_audio_filenames,
    apply_card_presentation,
    generate_guarded_word_audio,
)


class AudioGuardTests(unittest.TestCase):
    @staticmethod
    def _audio_for_duration(seconds):
        return b"x" * (44 + round(seconds * 48_000 / 8))

    def test_normal_generative_clip_is_not_retried(self):
        calls = []
        normal = self._audio_for_duration(0.82)

        def synthesize(*args, **kwargs):
            calls.append((args, kwargs))
            return normal

        result = generate_guarded_word_audio(
            "il sasso",
            "Beatrice",
            "it-IT",
            "access",
            "secret",
            engine="generative",
            generate_audio_func=synthesize,
        )

        self.assertIs(result, normal)
        self.assertEqual(len(calls), 1)

    def test_suspicious_clip_is_retried_and_shorter_result_wins(self):
        suspicious = self._audio_for_duration(1.75)
        normal = self._audio_for_duration(0.78)
        outputs = iter((suspicious, normal))
        calls = []

        def synthesize(*args, **kwargs):
            calls.append((args, kwargs))
            return next(outputs)

        result = generate_guarded_word_audio(
            "il sasso",
            "Beatrice",
            "it-IT",
            "access",
            "secret",
            engine="generative",
            generate_audio_func=synthesize,
        )

        self.assertIs(result, normal)
        self.assertEqual(len(calls), 2)

    def test_shortest_retry_is_kept_if_all_attempts_are_suspicious(self):
        outputs = [
            self._audio_for_duration(1.80),
            self._audio_for_duration(1.55),
            self._audio_for_duration(1.65),
        ]
        expected = outputs[1]
        iterator = iter(outputs)

        result = generate_guarded_word_audio(
            "il sasso",
            "Beatrice",
            "it-IT",
            "access",
            "secret",
            engine="generative",
            generate_audio_func=lambda *args, **kwargs: next(iterator),
        )

        self.assertIs(result, expected)

    def test_non_generative_audio_is_never_retried(self):
        calls = []
        suspicious = self._audio_for_duration(2.0)

        def synthesize(*args, **kwargs):
            calls.append((args, kwargs))
            return suspicious

        result = generate_guarded_word_audio(
            "il sasso",
            "Bianca",
            "it-IT",
            "access",
            "secret",
            engine="neural",
            generate_audio_func=synthesize,
        )

        self.assertIs(result, suspicious)
        self.assertEqual(len(calls), 1)

    def test_complete_visible_english_meaning_is_used_for_audio(self):
        data = {
            "tts_meaning_en": "nightmare",
            "back_html": (
                "<div>nightmare; incubus "
                f"{ENGLISH_MEANING_AUDIO_MARKER}"
                " <span>(کابوس)</span></div>"
            ),
        }

        _sync_english_meaning_audio_text(data)

        self.assertEqual(data["tts_meaning_en"], "nightmare; incubus")

    def test_english_meaning_extraction_decodes_safe_html(self):
        back_html = (
            "<div>rock &amp; stone; pebble "
            f"{ENGLISH_MEANING_AUDIO_MARKER}</div>"
        )

        self.assertEqual(
            _extract_visible_english_meaning(back_html),
            "rock & stone; pebble",
        )

    def test_structured_meaning_controls_english_audio(self):
        data = {
            "meaning_en": "filling out; compilation",
            "tts_meaning_en": "filling out",
            "back_html": "<div>incorrect</div>",
        }

        _sync_english_meaning_audio_text(data)

        self.assertEqual(
            data["tts_meaning_en"],
            "filling out; compilation",
        )

    def test_bilingual_main_meaning_renders_persian_on_own_line(self):
        data = {
            "meaning_en": "filling out; compilation",
            "meaning_fa": "پر کردن؛ تدوین",
            "back_html": (
                f"{MAIN_MEANING_START}<div>model output "
                f"{ENGLISH_MEANING_AUDIO_MARKER}</div>{MAIN_MEANING_END}"
                "<div>noun</div>"
            ),
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

        back_html = result["back_html"]
        self.assertIn("filling out; compilation", back_html)
        self.assertIn("پر کردن؛ تدوین", back_html)
        self.assertIn('class="anki-fa anki-fa-block"', back_html)
        self.assertNotIn("model output", back_html)

    def test_audio_filenames_change_with_content_and_update_card_html(self):
        data = {
            "word": "compilazione",
            "back_html": (
                "[sound:compilazione.mp3]"
                '<audio src="compilazione_example.mp3"></audio>'
                '<audio src="compilazione_meaning_en.mp3"></audio>'
            ),
            "production_card_html": {
                "front_html": "front",
                "back_html": '<audio src="compilazione_example.mp3"></audio>',
            },
        }
        audios = {
            "": b"word audio",
            "_example": b"example audio",
            "_meaning_en": b"meaning audio",
        }

        filenames = apply_versioned_audio_filenames(data, audios)

        self.assertRegex(
            filenames[""],
            r"^compilazione--[0-9a-f]{12}\.mp3$",
        )
        self.assertIn(filenames[""], data["back_html"])
        self.assertIn(filenames["_example"], data["back_html"])
        self.assertIn(filenames["_meaning_en"], data["back_html"])
        self.assertIn(
            filenames["_example"],
            data["production_card_html"]["back_html"],
        )

        second = {"word": "compilazione", "back_html": ""}
        second_filenames = apply_versioned_audio_filenames(
            second,
            {"": b"different word audio"},
        )
        self.assertNotEqual(filenames[""], second_filenames[""])


if __name__ == "__main__":
    unittest.main()
