import unittest

from main import _reconcile_target_results


def feedback_with(transcript, targets):
    return {
        "transcript_it": transcript,
        "retry_needed": any(not t.get("correct") for t in targets),
        "focus": {"category": "missing_word"},
        "target_results": targets,
    }


class ReconcileTargetResultsTests(unittest.TestCase):
    def test_transcribed_target_is_never_reported_missing(self):
        """The exact reported bug: 'intanto' is in the transcript yet the
        target evaluation claimed it was not used."""
        feedback = feedback_with(
            "fai la spesa, intanto pulisco la cucina",
            [{
                "word": "intanto",
                "used": False,
                "correct": False,
                "error_type": "not_used",
                "feedback_en": "You didn't use the target word 'intanto'.",
                "feedback_fa": "کلمه هدف استفاده نشد.",
            }],
        )

        changed = _reconcile_target_results(
            feedback, feedback["transcript_it"]
        )

        self.assertTrue(changed)
        result = feedback["target_results"][0]
        self.assertTrue(result["used"])
        self.assertTrue(result["correct"])
        self.assertEqual(result["error_type"], "none")
        # A transcript that fully passes lifts the retry banner.
        self.assertFalse(feedback["retry_needed"])
        self.assertEqual(feedback["focus"]["category"], "none")

    def test_word_boundaries_are_respected(self):
        feedback = feedback_with(
            "la vendetta è mia",
            [{
                "word": "ende",
                "used": False,
                "correct": False,
                "error_type": "not_used",
                "feedback_en": "missing",
                "feedback_fa": "غایب",
            }],
        )

        _reconcile_target_results(feedback, feedback["transcript_it"])

        self.assertFalse(feedback["target_results"][0]["used"])

    def test_genuinely_missing_target_stays_repairable(self):
        feedback = feedback_with(
            "vado a casa",
            [{
                "word": "intanto",
                "used": False,
                "correct": False,
                "error_type": "not_used",
                "feedback_en": "missing",
                "feedback_fa": "غایب",
            }],
        )

        changed = _reconcile_target_results(feedback, feedback["transcript_it"])

        self.assertFalse(changed)
        self.assertFalse(feedback["target_results"][0]["correct"])
        self.assertTrue(feedback["retry_needed"])

    def test_one_fixed_target_keeps_retry_for_the_other(self):
        feedback = feedback_with(
            "intanto pulisco la cucina",
            [
                {
                    "word": "intanto",
                    "used": False,
                    "correct": False,
                    "error_type": "not_used",
                    "feedback_en": "missing",
                    "feedback_fa": "غایب",
                },
                {
                    "word": "mentre",
                    "used": False,
                    "correct": False,
                    "error_type": "not_used",
                    "feedback_en": "missing",
                    "feedback_fa": "غایب",
                },
            ],
        )

        _reconcile_target_results(feedback, feedback["transcript_it"])

        self.assertTrue(feedback["target_results"][0]["correct"])
        self.assertFalse(feedback["target_results"][1]["correct"])
        self.assertTrue(feedback["retry_needed"])

    def test_empty_transcript_changes_nothing(self):
        feedback = feedback_with(
            "",
            [{
                "word": "intanto",
                "used": False,
                "correct": False,
                "error_type": "not_used",
                "feedback_en": "missing",
                "feedback_fa": "غایب",
            }],
        )

        self.assertFalse(_reconcile_target_results(feedback, ""))


if __name__ == "__main__":
    unittest.main()
