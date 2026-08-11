import unittest

from main import (
    PRODUCTION_TEMPLATE_BACK,
    PRODUCTION_WORD_AUDIO_TEMPLATE_MARKER,
    build_production_card_html,
)


class ProductionCardTests(unittest.TestCase):
    def test_template_has_legacy_word_audio_fallback(self):
        self.assertIn(PRODUCTION_WORD_AUDIO_TEMPLATE_MARKER, PRODUCTION_TEMPLATE_BACK)
        self.assertIn("{{WordAudio}}", PRODUCTION_TEMPLATE_BACK)
        self.assertIn(
            "anki-generator-production-word-audio-fallback",
            PRODUCTION_TEMPLATE_BACK,
        )

    def test_repairs_gap_using_pronoun_prefixed_conjugation(self):
        data = {
            "word": "proteggere",
            "tts_word": "proteggere",
            "tts_example": "Il casco protegge la testa.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "io proteggo",
            "tts_verb_2": "tu proteggi",
            "tts_verb_3": "lui/lei protegge",
            "tts_verb_4": "noi proteggiamo",
            "tts_verb_5": "voi proteggete",
            "tts_verb_6": "loro proteggono",
            "smart_grammar": {
                "past_participle": "protetto",
            },
            "production_card": {
                "cue_en": "to protect",
                "cue_fa": "محافظت کردن",
                # The model changed punctuation, so this supplied gap is not
                # an exact reconstruction of tts_example.
                "sentence_gap": "Il casco _____ la testa!",
                "missing_form": "protegge",
            },
        }

        card = build_production_card_html(
            data,
            "Both (English + Persian)",
            "Italian",
        )

        self.assertIn("Il casco ", card["front_html"])
        self.assertIn("_____</span> la testa.", card["front_html"])
        self.assertIn(">protegge</span> la testa.", card["back_html"])
        self.assertIn(
            "anki-generator-production-word-audio",
            card["back_html"],
        )
        self.assertIn('data-audio-suffix=""', card["back_html"])
        self.assertIn("proteggere.mp3", card["back_html"])

    def test_repairs_noun_gap_from_exact_spoken_example(self):
        data = {
            "word": "armadio",
            "tts_word": "l'armadio",
            "tts_example": "L'armadio è pieno.",
            "word_family_main_part_of_speech": "noun",
            "smart_grammar": {
                "plural": "gli armadi",
            },
            "production_card": {
                "cue_en": "wardrobe",
                "cue_fa": "کمد",
                "sentence_gap": "Ho aperto _____.",
                "missing_form": "armadio",
            },
        }

        card = build_production_card_html(
            data,
            "Both (English + Persian)",
            "Italian",
        )

        self.assertIn("L&#x27;", card["front_html"])
        self.assertIn("_____</span> è pieno.", card["front_html"])
        self.assertIn(">armadio</span> è pieno.", card["back_html"])

    def test_repairs_target_inside_model_supplied_contraction(self):
        data = {
            "word": "armadio",
            "tts_word": "l'armadio",
            "tts_example": "Ho messo la giacca nell'armadio.",
            "word_family_main_part_of_speech": "noun",
            "smart_grammar": {
                "plural": "gli armadi",
            },
            "production_card": {
                "cue_en": "wardrobe",
                "cue_fa": "کمد",
                "sentence_gap": "Ho messo la giacca _____.",
                "missing_form": "nell'armadio",
            },
        }

        card = build_production_card_html(
            data,
            "Both (English + Persian)",
            "Italian",
        )

        self.assertIn("nell&#x27;", card["front_html"])
        self.assertIn("_____</span>.", card["front_html"])
        self.assertIn(">armadio</span>.", card["back_html"])

    def test_accepts_verified_italian_infinitive_clitic_form(self):
        data = {
            "word": "proteggere",
            "tts_word": "proteggere",
            "tts_example": "Devo proteggermi dal sole.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "io proteggo",
            "tts_verb_2": "tu proteggi",
            "tts_verb_3": "lui, lei protegge",
            "tts_verb_4": "noi proteggiamo",
            "tts_verb_5": "voi proteggete",
            "tts_verb_6": "loro proteggono",
            "smart_grammar": {
                "past_participle": "protetto",
            },
            "production_card": {
                "cue_en": "to protect",
                "cue_fa": "محافظت کردن",
                "sentence_gap": "Devo _____ dal sole.",
                "missing_form": "proteggermi",
            },
        }

        card = build_production_card_html(
            data,
            "Both (English + Persian)",
            "Italian",
        )

        self.assertIn("Devo ", card["front_html"])
        self.assertIn("_____</span> dal sole.", card["front_html"])
        self.assertIn(">proteggermi</span> dal sole.", card["back_html"])

    def test_accepts_regular_italian_gerund(self):
        data = {
            "word": "imparare",
            "tts_word": "imparare",
            "tts_example": "Sto imparando l'italiano.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "imparo",
            "tts_verb_2": "impari",
            "tts_verb_3": "impara",
            "tts_verb_4": "impariamo",
            "tts_verb_5": "imparate",
            "tts_verb_6": "imparano",
            "smart_grammar": {
                "past_participle": "imparato",
            },
            "production_card": {
                "cue_en": "I am learning Italian.",
                "cue_fa": "من دارم ایتالیایی یاد می‌گیرم.",
                "sentence_gap": "Sto _____ l'italiano.",
                "missing_form": "imparando",
            },
        }

        card = build_production_card_html(data, "English", "Italian")

        self.assertIn("_____</span> l&#x27;italiano.", card["front_html"])
        self.assertIn(">imparando</span> l&#x27;italiano.", card["back_html"])

    def test_accepts_plural_agreement_of_supplied_past_participle(self):
        data = {
            "word": "scattare",
            "tts_word": "scattare",
            "tts_example": "Sono scattati i controlli dei documenti.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "scatto",
            "tts_verb_2": "scatti",
            "tts_verb_3": "scatta",
            "tts_verb_4": "scattiamo",
            "tts_verb_5": "scattate",
            "tts_verb_6": "scattano",
            "smart_grammar": {
                "past_participle": "scattato",
            },
            "production_card": {
                "cue_en": "The checks were triggered.",
                "cue_fa": "کنترل‌ها آغاز شدند.",
                "sentence_gap": "Sono _____ i controlli dei documenti.",
                "missing_form": "scattati",
            },
        }

        card = build_production_card_html(data, "English", "Italian")

        self.assertIn("Sono ", card["front_html"])
        self.assertIn("_____</span> i controlli", card["front_html"])
        self.assertIn(">scattati</span> i controlli", card["back_html"])

    def test_accepts_italian_uno_adjective_apocope(self):
        data = {
            "word": "alcuno",
            "tts_word": "alcuno",
            "tts_example": "Non ho alcun problema.",
            "word_family_main_part_of_speech": "adjective",
            "smart_grammar": {
                "masculine_singular": "alcuno",
                "feminine_singular": "alcuna",
                "masculine_plural": "alcuni",
                "feminine_plural": "alcune",
            },
            "production_card": {
                "cue_en": "I don't have any problem.",
                "cue_fa": "من هیچ مشکلی ندارم.",
                "sentence_gap": "Non ho _____ problema.",
                "missing_form": "alcun",
            },
        }

        card = build_production_card_html(data, "English", "Italian")

        self.assertIn("Non ho ", card["front_html"])
        self.assertIn("_____</span> problema.", card["front_html"])
        self.assertIn(">alcun</span> problema.", card["back_html"])

    def test_accepts_reflexive_base_infinitive_after_pronoun(self):
        data = {
            "word": "lamentarsi",
            "tts_word": "lamentarsi",
            "tts_example": "Non ti lamentare sempre del tempo.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "mi lamento",
            "tts_verb_2": "ti lamenti",
            "tts_verb_3": "si lamenta",
            "tts_verb_4": "ci lamentiamo",
            "tts_verb_5": "vi lamentate",
            "tts_verb_6": "si lamentano",
            "smart_grammar": {
                "past_participle": "lamentato",
            },
            "production_card": {
                "cue_en": "to complain",
                "cue_fa": "شکایت کردن",
                "sentence_gap": "Non ti _____ sempre del tempo.",
                "missing_form": "lamentare",
            },
        }

        card = build_production_card_html(data, "English", "Italian")

        self.assertIn("Non ti ", card["front_html"])
        self.assertIn("_____</span> sempre del tempo.", card["front_html"])
        self.assertIn(">lamentare</span> sempre del tempo.", card["back_html"])

    def test_does_not_repair_gap_with_unrelated_example_word(self):
        data = {
            "word": "proteggere",
            "tts_word": "proteggere",
            "tts_example": "Il casco protegge la testa.",
            "word_family_main_part_of_speech": "verb",
            "tts_verb_1": "io proteggo",
            "tts_verb_2": "tu proteggi",
            "tts_verb_3": "lui/lei protegge",
            "tts_verb_4": "noi proteggiamo",
            "tts_verb_5": "voi proteggete",
            "tts_verb_6": "loro proteggono",
            "production_card": {
                "cue_en": "helmet",
                "cue_fa": "کلاه ایمنی",
                "sentence_gap": "Il _____ protegge la testa.",
                "missing_form": "casco",
            },
        }

        self.assertEqual(
            build_production_card_html(data, "English", "Italian"),
            {},
        )


if __name__ == "__main__":
    unittest.main()
