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

    def test_card_learning_boosters_are_in_prompt(self):
        prompt = SYSTEM_INSTRUCTION_TEMPLATE

        self.assertIn("## 🎒 Card learning boosters", prompt)
        self.assertIn("[EMOJI]", prompt)
        self.assertIn("[FREQ_CHIP]", prompt)
        self.assertIn("My sentence", prompt)
        # The "My sentence" block is static filler the learner replaces.
        self.assertIn("copy it unchanged with its italic placeholder line", prompt)
        # The keyword-method memory hook was removed from the card at the
        # user's request — it lives only in the Speaking Lab's 🧠 button.
        self.assertNotIn("Memory hook", prompt)
        self.assertNotIn("MEMORY_HOOK", prompt)

    def test_lab_mnemonic_generator_keeps_the_persian_keyword_guard(self):
        # The card no longer carries memory hooks, but the Speaking Lab's
        # mnemonic button must still reject Urdu/Hindi keywords (نمبر bug).
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("generate_word_mnemonic", source)
        self.assertIn("NEVER use an\n   Urdu or Hindi word", source)

    def test_forms_table_has_an_exact_verbatim_template(self):
        from pathlib import Path

        prompt = SYSTEM_INSTRUCTION_TEMPLATE

        self.assertIn("## 📋 Forms table (adjectives & nouns) — exact template", prompt)
        self.assertIn("[FORM_MS]", prompt)
        self.assertIn("[FORM_FP]", prompt)
        self.assertIn(
            "the alignment depends on this markup being verbatim", prompt
        )
        # Persian runs must use the bundled font: the card style forces it
        # globally, and the old Vazirmatn-only stack is banned everywhere.
        self.assertNotIn("font-family:'Vazirmatn',Tahoma", prompt)
        main_source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('[lang="fa"],[dir="rtl"]', main_source)
        self.assertIn('ANKI_CARD_STYLE_MARKER = "anki-generator-card-style-v4"', main_source)

    def test_learning_booster_fields_are_in_generation_schema(self):
        import re
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(
            encoding="utf-8"
        )
        for field in (
            '"emoji": {"type": "string"}',
            '"top500", "top1000", "top3000", "beyond3000"',
        ):
            self.assertIn(field, source)
        self.assertNotIn('"memory_hook_en"', source)
        # Boosters stay OPTIONAL: required_output_fields must not list them,
        # so older user-saved custom prompts still generate valid cards.
        required_block = re.search(
            r"required_output_fields = \[(.*?)\]", source, re.S
        )
        self.assertIsNotNone(required_block)
        self.assertNotIn("frequency_band", required_block.group(1))


if __name__ == "__main__":
    unittest.main()
