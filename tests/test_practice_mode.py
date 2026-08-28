import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import main
from practice_mode import (
    CORRECTION_FIELDS,
    CORRECTION_MODEL_NAME,
    CORRECTION_TEMPLATE_NAME,
    create_correction_cards,
    default_practice_state,
    discover_practice_candidates,
    load_practice_state,
    save_practice_state,
    select_practice_targets,
    update_practice_state,
)


class CandidateAnki:
    def __init__(self):
        self.cards = {
            11: {
                "cardId": 11,
                "note": 101,
                "modelName": "AG Production Recall v1",
                "reps": 8,
                "lapses": 2,
                "interval": 6,
                "factor": 2200,
            },
            12: {
                "cardId": 12,
                "note": 102,
                "modelName": "Italian Vocab",
                "reps": 20,
                "lapses": 0,
                "interval": 40,
                "factor": 2500,
            },
            13: {
                "cardId": 13,
                "note": 103,
                "modelName": "AG Production Recall v1",
                "reps": 0,
                "lapses": 0,
                "interval": 0,
                "factor": 0,
            },
            14: {
                "cardId": 14,
                "note": 104,
                "modelName": "Foreign",
                "reps": 10,
                "lapses": 5,
                "interval": 3,
                "factor": 1800,
            },
        }
        self.notes = {
            101: self._note(
                101,
                "AG Production Recall v1",
                {
                    "Word": "nascita",
                    "ProductionFront": "<div>birth</div>",
                    "ProductionBack": (
                        "<style>.secret{}</style><div>la nascita</div>"
                        "<script>bad()</script><div>data di nascita</div>"
                    ),
                },
            ),
            102: self._note(
                102,
                "Italian Vocab",
                {
                    "Word": "entro",
                    "AG_ProductionFront_v1": "<div>by; within</div>",
                    "AG_ProductionBack_v1": "<div>entro venerdì</div>",
                },
            ),
            103: self._note(
                103,
                "AG Production Recall v1",
                {
                    "Word": "nuovo",
                    "ProductionFront": "new",
                    "ProductionBack": "nuovo",
                },
            ),
            104: self._note(104, "Foreign", {"Word": "ignore"}),
        }

    @staticmethod
    def _note(note_id, model_name, values):
        return {
            "noteId": note_id,
            "modelName": model_name,
            "fields": {
                name: {"value": value, "order": index}
                for index, (name, value) in enumerate(values.items())
            },
        }

    def __call__(self, action, params=None):
        params = params or {}
        if action == "findCards":
            self.assert_query(params["query"])
            return list(self.cards)
        if action == "cardsInfo":
            return [copy.deepcopy(self.cards[value]) for value in params["cards"]]
        if action == "notesInfo":
            return [copy.deepcopy(self.notes[value]) for value in params["notes"]]
        raise AssertionError(action)

    @staticmethod
    def assert_query(query):
        if 'card:"AG Production Recall"' not in query or "-is:new" not in query:
            raise AssertionError(query)


class PracticeCandidateTests(unittest.TestCase):
    def test_discovers_only_studied_owned_production_cards(self):
        candidates = discover_practice_candidates(
            CandidateAnki(),
            source_model_name="Italian Vocab",
            recall_model_name="AG Production Recall v1",
        )

        self.assertEqual({item["word"] for item in candidates}, {"nascita", "entro"})
        nascita = next(item for item in candidates if item["word"] == "nascita")
        self.assertNotIn("bad()", nascita["reference"])
        self.assertNotIn(".secret", nascita["reference"])
        self.assertGreater(nascita["weakness"], 0)

    def test_selection_rotates_recent_words_and_keeps_mature_transfer(self):
        candidates = [
            {
                "word": f"word-{index}",
                "identity": f"word-{index}",
                "weakness": float(100 - index),
                "interval": 3 if index < 4 else 40,
            }
            for index in range(6)
        ]
        state = default_practice_state()
        state["recent_words"] = ["word-0", "word-1"]

        selected = select_practice_targets(
            candidates,
            state,
            count=3,
            today=date(2026, 8, 10),
        )

        identities = {item["identity"] for item in selected}
        self.assertFalse({"word-0", "word-1"}.intersection(identities))
        self.assertTrue(any(item["interval"] >= 21 for item in selected))


class PracticeStateTests(unittest.TestCase):
    def test_state_is_atomic_and_same_error_is_offered_on_second_occurrence(self):
        targets = [{
            "word": "entro",
            "identity": "entro",
            "card_id": 12,
        }]
        feedback = {
            "_gemini_model": "test-model",
            "target_results": [{
                "word": "entro",
                "correct": False,
                "error_type": "collocation",
                "feedback_en": "Use it with a deadline.",
                "feedback_fa": "آن را با مهلت به کار ببر.",
                "correction_prompt_en": "Say that it must arrive by Friday.",
                "correction_prompt_fa": "بگو باید تا جمعه برسد.",
                "correction_answer_it": "Deve arrivare entro venerdì.",
            }],
        }
        state = default_practice_state()

        first = update_practice_state(state, targets, feedback)
        second = update_practice_state(state, targets, feedback)

        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["error_type"], "collocation")
        self.assertEqual(state["sessions_completed"], 2)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            path = save_practice_state(workspace, state)
            loaded = load_practice_state(workspace)
            self.assertTrue(path.is_file())
            self.assertEqual(loaded["sessions_completed"], 2)

    def test_correct_use_resets_the_repeated_error_count(self):
        state = default_practice_state()
        state["mistakes"]["entro|collocation"] = {
            "word": "entro",
            "error_type": "collocation",
            "count": 1,
        }
        targets = [{"word": "entro", "identity": "entro", "card_id": 12}]
        feedback = {
            "target_results": [{
                "word": "entro",
                "correct": True,
                "error_type": "none",
            }],
        }

        update_practice_state(state, targets, feedback)

        self.assertEqual(state["mistakes"]["entro|collocation"]["count"], 0)


class CorrectionAnki:
    def __init__(self):
        self.models = {}
        self.notes = []
        self.calls = []

    def __call__(self, action, params=None):
        params = copy.deepcopy(params or {})
        self.calls.append((action, params))
        if action == "modelNamesAndIds":
            return {name: model["id"] for name, model in self.models.items()}
        if action == "createModel":
            self.models[params["modelName"]] = {
                "id": 7,
                "fields": list(params["inOrderFields"]),
                "templates": {
                    value["Name"]: {
                        "Front": value["Front"],
                        "Back": value["Back"],
                    }
                    for value in params["cardTemplates"]
                },
                "css": params["css"],
            }
            return {"id": 7}
        if action == "modelFieldNames":
            return self.models[params["modelName"]]["fields"]
        if action == "modelTemplates":
            return self.models[params["modelName"]]["templates"]
        if action == "modelStyling":
            return {"css": self.models[params["modelName"]]["css"]}
        if action == "createDeck":
            return 9
        if action == "findNotes":
            return []
        if action == "addNote":
            self.notes.append(params["note"])
            return 100 + len(self.notes)
        raise AssertionError(action)


class CorrectionCardTests(unittest.TestCase):
    def test_creates_isolated_card_only_after_function_is_called(self):
        fake = CorrectionAnki()
        entry = {
            "word": "entro",
            "error_type": "collocation",
            "source_card_id": 12,
            "correction_prompt_en": "Say it must arrive by Friday.",
            "correction_prompt_fa": "بگو باید تا جمعه برسد.",
            "correction_answer_it": "Deve arrivare entro venerdì.",
            "feedback_en": "Use entro with a deadline.",
            "feedback_fa": "از entro برای مهلت استفاده کن.",
        }

        result = create_correction_cards(fake, [entry], source_deck="Italian")

        self.assertEqual(result, {"added": 1, "skipped": 0})
        self.assertIn(CORRECTION_MODEL_NAME, fake.models)
        self.assertEqual(fake.models[CORRECTION_MODEL_NAME]["fields"], list(CORRECTION_FIELDS))
        self.assertIn(CORRECTION_TEMPLATE_NAME, fake.models[CORRECTION_MODEL_NAME]["templates"])
        self.assertEqual(fake.notes[0]["deckName"], "Italian::Practice Corrections")
        self.assertEqual(fake.notes[0]["fields"]["AG_SourceCardID"], "12")


class PracticeFeedbackTests(unittest.TestCase):
    def test_feedback_uses_one_structured_gemini_call_and_preserves_targets(self):
        payload = {
            "overall_en": "Good attempt.",
            "overall_fa": "تلاش خوبی بود.",
            "strengths": ["Clear message"],
            "corrected_response_it": "Deve arrivare entro venerdì.",
            "retry_needed": False,
            "retry_instruction_en": "",
            "retry_instruction_fa": "",
            "target_results": [{
                "word": "entro",
                "used": True,
                "correct": True,
                "error_type": "none",
                "feedback_en": "Correct deadline use.",
                "feedback_fa": "کاربرد مهلت درست است.",
                "correction_prompt_en": "",
                "correction_prompt_fa": "",
                "correction_answer_it": "",
            }],
        }
        response = type("Response", (), {"text": json.dumps(payload)})()
        client = object()
        with patch.object(main.genai, "Client", return_value=client) as client_class, patch.object(
            main,
            "generate_with_gemini_fallback",
            return_value=(response, "gemini-test"),
        ) as generate:
            result = main.generate_practice_feedback(
                [{"word": "entro", "reference": "by a deadline"}],
                {
                    "title": "Ask",
                    "prompt_en": "Ask for information.",
                    "prompt_fa": "اطلاعات بخواه.",
                },
                "Deve arrivare entro venerdì.",
                "key",
            )

        self.assertEqual(result["_gemini_model"], "gemini-test")
        self.assertEqual(result["target_results"][0]["word"], "entro")
        client_class.assert_called_once()
        generate.assert_called_once()
        config = generate.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")

