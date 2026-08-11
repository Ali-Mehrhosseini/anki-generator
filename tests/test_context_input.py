import unittest

from main import (
    CONTEXT_USAGE_INSTRUCTION,
    _context_example_uses_input_form,
    build_contextual_request,
)


class ContextInputTests(unittest.TestCase):
    def test_context_example_must_reuse_inflected_target_form(self):
        context = "Sono scattati anche all'aeroporto i controlli."

        self.assertTrue(
            _context_example_uses_input_form(
                "scattati",
                context,
                "Sono scattati i controlli dei documenti.",
            )
        )
        self.assertFalse(
            _context_example_uses_input_form(
                "scattati",
                context,
                "Voglio scattare una foto.",
            )
        )

    def test_context_instruction_prefers_simple_matching_gloss(self):
        self.assertIn("one simple, high-frequency beginner gloss", CONTEXT_USAGE_INSTRUCTION)
        self.assertIn("the checks started", CONTEXT_USAGE_INSTRUCTION)
        self.assertIn("Conjugation translations", CONTEXT_USAGE_INSTRUCTION)

    def test_no_context_preserves_original_request(self):
        contents, instruction = build_contextual_request("entro", None)

        self.assertEqual(contents, "entro")
        self.assertEqual(instruction, "")

    def test_context_keeps_target_separate_from_surrounding_text(self):
        contents, instruction = build_contextual_request(
            "entro",
            "Al momento è offerto entro i 27 anni.",
        )

        self.assertIn("TARGET_WORD:\nentro", contents)
        self.assertIn("<USAGE_CONTEXT>", contents)
        self.assertIn("entro i 27 anni", contents)
        self.assertEqual(instruction, CONTEXT_USAGE_INSTRUCTION)
        self.assertIn("Create a card only for TARGET_WORD", instruction)
        self.assertIn("highest-priority evidence", instruction)

    def test_context_length_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "4,000"):
            build_contextual_request("entro", "x" * 4_001)


if __name__ == "__main__":
    unittest.main()
