import tempfile
import unittest
from pathlib import Path

from error_insights import collect_errors
from learning_lab import (
    default_state,
    load_state,
    record_word_help,
    save_state,
)


class WordHelpEventTests(unittest.TestCase):
    def test_peek_guess_reveal_counts_accumulate(self):
        state = default_state()
        record_word_help(state, "Scelta", "peek")
        record_word_help(state, "scelta", "guess", guessed_correctly=False)
        record_word_help(state, "scelta", "guess", guessed_correctly=True)
        entry = record_word_help(state, "Scelta", "reveal")

        self.assertEqual(entry["peeks"], 1)
        self.assertEqual(entry["guesses"], 2)
        self.assertEqual(entry["correct_guesses"], 1)
        self.assertEqual(entry["reveals"], 1)
        # The display form of the most recent event wins.
        self.assertEqual(entry["word"], "Scelta")

    def test_unknown_events_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported word-help event"):
            record_word_help(default_state(), "scelta", "party")

    def test_empty_words_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "No word was provided"):
            record_word_help(default_state(), "  ", "peek")

    def test_lookup_table_stays_bounded(self):
        state = default_state()
        for index in range(70):
            record_word_help(state, f"word{index}", "peek")

        self.assertEqual(len(state["word_lookups"]), 60)


class WordLookupInsightTests(unittest.TestCase):
    def test_repeated_lookups_reach_the_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = default_state()
            record_word_help(state, "scelta", "peek")
            record_word_help(state, "scelta", "guess", guessed_correctly=False)
            record_word_help(state, "scelta", "reveal")
            record_word_help(state, "facile", "peek")
            save_state(workspace, state)

            result = collect_errors(workspace)

        lookup_patterns = [
            pattern for pattern in result["patterns"]
            if pattern["error_type"] == "word_lookup"
        ]
        self.assertEqual(len(lookup_patterns), 1)
        self.assertEqual(lookup_patterns[0]["label"], "scelta")
        # Gap strength counts peeks and reveals; wrong guesses are covered
        # by the reveal they usually lead to.
        self.assertEqual(lookup_patterns[0]["count"], 2)
        # One curious peek never becomes a "pattern".
        self.assertNotIn("facile", {p["label"] for p in result["patterns"]})

    def test_words_you_keep_guessing_right_are_not_flagged(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = default_state()
            for _ in range(3):
                record_word_help(state, "casa", "peek")
                record_word_help(state, "casa", "guess", guessed_correctly=True)
            save_state(workspace, state)

            result = collect_errors(workspace)

        self.assertEqual(
            [p for p in result["patterns"] if p["error_type"] == "word_lookup"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
