import unittest

from main import SYSTEM_INSTRUCTION_TEMPLATE


class PromptRuleTests(unittest.TestCase):
    def test_morphological_homograph_rule_offers_entro_choices(self):
        prompt = SYSTEM_INSTRUCTION_TEMPLATE

        self.assertIn("Morphological homographs — selection rule", prompt)
        self.assertIn(
            "Offer both `entro` (preposition) and `entrare` (verb)",
            prompt,
        )
        self.assertIn("leave verb-only fields empty", prompt)
        self.assertIn(
            "alternate grammatical analysis is mandatory",
            prompt,
        )

    def test_bilingual_glosses_must_be_semantically_parallel(self):
        prompt = SYSTEM_INSTRUCTION_TEMPLATE

        self.assertIn(
            "Keep English and Persian glosses semantically parallel",
            prompt,
        )
        self.assertIn("use `تدوین`", prompt)

    def test_word_origin_is_structured_and_never_guessed(self):
        prompt = SYSTEM_INSTRUCTION_TEMPLATE

        self.assertIn("## 🧬 Word origin data", prompt)
        self.assertIn("Never invent an origin", prompt)
        self.assertIn("[WORD_ORIGIN_HTML]", prompt)


if __name__ == "__main__":
    unittest.main()
