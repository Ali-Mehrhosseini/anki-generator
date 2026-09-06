import tempfile
import unittest
from pathlib import Path

from cli import _word_is_known
from grammar_practice import (
    create_dictogloss_session,
    dictogloss_session,
    record_dictogloss_result,
)
from main import generate_word_mnemonic, validate_dictogloss_text


class KeywordMnemonicTests(unittest.TestCase):
    def test_requires_api_key(self):
        result = generate_word_mnemonic("scelta", "choice", "")
        self.assertIn("error", result)

    def test_rejects_missing_word(self):
        result = generate_word_mnemonic("  ", "choice", "key")
        self.assertIn("error", result)

    def test_rejects_overlong_word(self):
        result = generate_word_mnemonic("x" * 61, "choice", "key")
        self.assertIn("error", result)


class DictoglossTextValidationTests(unittest.TestCase):
    def test_accepts_reasonable_text(self):
        data = validate_dictogloss_text({
            "text_it": "Ieri ho visitato mia nonna e le ho portato dei fiori. "
                       "Siamo rimasti a parlare per due ore insieme.",
            "translation_en": "Yesterday I visited my grandmother...",
            "grammar_focus_en": "passato prossimo with avere",
        })
        self.assertEqual(data["text_it"].count("."), 2)

    def test_rejects_too_short_text(self):
        with self.assertRaisesRegex(ValueError, "12 and 45"):
            validate_dictogloss_text({
                "text_it": "Ho mangiato pizza.",
                "translation_en": "",
                "grammar_focus_en": "",
            })

    def test_rejects_text_without_sentence_end(self):
        with self.assertRaisesRegex(ValueError, "complete sentences"):
            validate_dictogloss_text({
                "text_it": " ".join(["parola"] * 15),
                "translation_en": "",
                "grammar_focus_en": "",
            })


class DictoglossSessionTests(unittest.TestCase):
    TOPIC = {
        "topic_key": "passato_prossimo",
        "topic": "Passato prossimo",
        "level": "A2",
        "rule_en": "auxiliary choice",
    }
    TEXT = {
        "text_it": "Ieri ho visitato mia nonna e le ho portato dei fiori. "
                   "Siamo rimasti a parlare per due ore insieme.",
        "translation_en": "Yesterday I visited my grandmother...",
        "grammar_focus_en": "passato prossimo",
    }

    def test_original_text_stays_server_side(self):
        with tempfile.TemporaryDirectory() as directory:
            session_id = create_dictogloss_session(self.TOPIC, dict(self.TEXT))
            session = dictogloss_session(session_id)

            self.assertEqual(session["text_it"], self.TEXT["text_it"])
            self.assertEqual(session["attempts"], 0)
            # The public record flow is the only path that reveals it.
            self.assertNotIn("text_it", self.TOPIC)

    def test_failed_attempt_hides_original_then_reveals(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session_id = create_dictogloss_session(self.TOPIC, dict(self.TEXT))

            first = record_dictogloss_result(
                workspace,
                session_id,
                "Ieri visitato nonna e portato fiori.",
                {"correct": False, "error_type": "tense_mood"},
            )
            self.assertTrue(first["retry_required"])
            self.assertNotIn("text_it", first)

            second = record_dictogloss_result(
                workspace,
                session_id,
                "Ieri ho visitato mia nonna.",
                {"correct": False, "error_type": "word_order"},
            )
            self.assertFalse(second["retry_required"])
            self.assertEqual(second["text_it"], self.TEXT["text_it"])
            self.assertEqual(second["attempt_number"], 2)

            state_error = None
            try:
                from grammar_practice import load_state
                stats = load_state(workspace)["topic_stats"]["passato_prossimo"]
                self.assertEqual(stats["dictogloss_attempts"], 2)
                self.assertEqual(stats["dictogloss_correct"], 0)
            except Exception as error:  # pragma: no cover
                state_error = error
            self.assertIsNone(state_error)

    def test_correct_attempt_counts_and_reveals(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session_id = create_dictogloss_session(self.TOPIC, dict(self.TEXT))
            result = record_dictogloss_result(
                workspace,
                session_id,
                self.TEXT["text_it"],
                {"correct": True, "error_type": "none"},
            )

            self.assertTrue(result["correct"])
            self.assertFalse(result["retry_required"])
            self.assertEqual(result["text_it"], self.TEXT["text_it"])

    def test_expired_session_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "expired"):
                record_dictogloss_result(
                    Path(directory),
                    "nonesuch",
                    "text",
                    {"correct": True},
                )


class TeachCoverageTests(unittest.TestCase):
    KNOWN = {"luce", "dormire", "spengo", "casa"}

    def test_plural_and_inflection_match_the_lemma(self):
        self.assertTrue(_word_is_known("luci", self.KNOWN))
        self.assertTrue(_word_is_known("dormirebbe", self.KNOWN))
        self.assertTrue(_word_is_known("casa", self.KNOWN))

    def test_genuinely_new_words_do_not_match(self):
        self.assertFalse(_word_is_known("tavolo", self.KNOWN))
        self.assertFalse(_word_is_known("finestra", self.KNOWN))


if __name__ == "__main__":
    unittest.main()
