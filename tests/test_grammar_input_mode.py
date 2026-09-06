import json
import tempfile
import unittest
from pathlib import Path

from grammar_practice import (
    anki_metadata_fields,
    check_controlled_answer,
    create_session,
    load_state,
    mastery_by_topic,
    practice_payload_for_card,
    session_conversation_context,
    session_item_context,
    session_summary,
    list_conversation_scenarios,
)
from main import validate_grammar_card_set


def input_card(card_id="input_gli_1", answer_index=0):
    return {
        "card_id": card_id,
        "mode": "input",
        "target_form": "gli",
        "input_sentence": "Ho visto Luca e gli ho dato le chiavi.",
        "input_sentence_en": "I saw Luca and gave him the keys.",
        "input_sentence_fa": "لوکا را دیدم و کلیدها را به او دادم.",
        "interpretation_prompt_en": "Who received the keys?",
        "interpretation_prompt_fa": "چه کسی کلیدها را گرفت؟",
        "answer_options": ["Luca", "the speaker"],
        "answer_index": answer_index,
        "form_meaning_en": "'gli' means 'to him', so the keys went to Luca.",
        "form_meaning_fa": "«gli» یعنی «به او».",
        "front_html": (
            "<div>Ho visto Luca e gli ho dato le chiavi.</div>"
            "<div>Who received the keys?</div>"
        ),
        "back_html": "<div>Luca</div>",
        "tts_sentence": "Ho visto Luca e gli ho dato le chiavi.",
    }


def input_deck(topic="Pronomi indiretti", key="pronomi_indiretti"):
    return {
        "mode": "input",
        "topic": topic,
        "_topic_key": key,
        "level": "A2",
    }


class FakeGrammarAnki:
    def __init__(self, card, card_deck):
        metadata = anki_metadata_fields(card, card_deck, 1)
        self.notes = [{
            "noteId": 1,
            "cards": [11],
            "fields": {
                name: {"value": value} for name, value in metadata.items()
            },
        }]
        self.cards = [{
            "cardId": 11,
            "note": 1,
            "reps": 0,
            "lapses": 0,
            "interval": 0,
            "factor": 2500,
        }]

    def __call__(self, action, params=None):
        params = params or {}
        if action == "findNotes":
            return [note["noteId"] for note in self.notes]
        if action == "notesInfo":
            wanted = set(params["notes"])
            return [note for note in self.notes if note["noteId"] in wanted]
        if action == "cardsInfo":
            wanted = set(params["cards"])
            return [card for card in self.cards if card["cardId"] in wanted]
        raise AssertionError(action)


class InputModeValidationTests(unittest.TestCase):
    def test_validator_accepts_complete_input_set(self):
        cards = [input_card(f"input_card_{index}") for index in range(4)]
        data = {"cards": cards}

        validated = validate_grammar_card_set(data, "input")

        self.assertEqual(validated["cards"][0]["answer_index"], 0)

    def test_validator_rejects_input_card_without_valid_index(self):
        cards = [input_card(f"input_card_{index}", answer_index=5) for index in range(4)]
        data = {"cards": cards}

        with self.assertRaisesRegex(ValueError, "points outside"):
            validate_grammar_card_set(data, "input")

    def test_validator_rejects_duplicate_interpretations(self):
        card = input_card("dup_1")
        card["answer_options"] = ["Luca", "luca"]
        cards = [dict(card, card_id=f"dup_{index}") for index in range(4)]
        data = {"cards": cards}

        with self.assertRaisesRegex(ValueError, "duplicate interpretations"):
            validate_grammar_card_set(data, "input")

    def test_payload_keeps_correct_answer_server_side_only(self):
        payload = practice_payload_for_card(input_card(), input_deck(), 1)

        self.assertEqual(payload["answers"], ["Luca"])
        self.assertEqual(payload["answer_options"], ["Luca", "the speaker"])
        self.assertNotIn("answer_index", payload)
        self.assertEqual(payload["mode"], "input")

    def test_public_metadata_stores_only_the_correct_option(self):
        fields = anki_metadata_fields(input_card(), input_deck(), 1)
        payload = json.loads(fields["AG_PracticeData"])

        self.assertEqual(fields["AG_Answer"], "Luca")
        self.assertEqual(payload["answers"], ["Luca"])


class InputStagePracticeTests(unittest.TestCase):
    def test_input_answers_route_to_input_stage(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            first = check_controlled_answer(
                workspace, session["session_id"], 0, ["the speaker"]
            )
            second = check_controlled_answer(
                workspace, session["session_id"], 0, ["Luca"]
            )
            stats = load_state(workspace)["topic_stats"]["pronomi_indiretti"]

            self.assertTrue(first["retry_required"])
            self.assertTrue(second["correct"])
            self.assertEqual(stats["input_attempts"], 2)
            self.assertEqual(stats["input_first_try_correct"], 0)
            self.assertEqual(stats.get("controlled_attempts", 0), 0)
            errors = load_state(workspace)["error_notebook"]
            self.assertEqual(next(iter(errors.values()))["stage"], "input")

    def test_input_case_and_punctuation_are_tolerated(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            result = check_controlled_answer(
                workspace, session["session_id"], 0, [" luca. "]
            )

            self.assertTrue(result["correct"])

    def test_mastery_includes_input_stage_for_topics_with_input_cards(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            check_controlled_answer(
                workspace, session["session_id"], 0, ["the speaker"]
            )
            check_controlled_answer(
                workspace, session["session_id"], 0, ["Luca"]
            )
            mastery = mastery_by_topic(fake, workspace)

        stages = mastery["pronomi_indiretti"]["stages"]
        self.assertIn("input", stages)
        self.assertEqual(stages["input"], 0)
        self.assertEqual(mastery["pronomi_indiretti"]["status"], "new")

    def test_summary_reports_input_and_repair_candidates(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            session_id = session["session_id"]
            check_controlled_answer(workspace, session_id, 0, ["the speaker"])
            summary = session_summary(workspace, session_id)

        self.assertEqual(summary["input_items"], 1)
        self.assertEqual(summary["stage_accuracy"]["input"], 0)
        self.assertEqual(summary["repair_candidates"], ["pronomi_indiretti"])
        self.assertEqual(summary["topic_report"][0]["input_misses"], 1)

    def test_explanation_context_hides_the_answer(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            context = session_item_context(
                workspace, session["session_id"], 0, ["the speaker"]
            )

        self.assertEqual(context["kind"], "controlled")
        self.assertEqual(context["learner_response"], "the speaker")
        self.assertNotIn("answers", context)
        # The form→meaning rule names the correct interpretation, so it is
        # withheld from the explanation prompt for input items.
        self.assertEqual(context["rule_en"], "")

    def test_input_rule_stays_hidden_until_reveal(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            session_id = session["session_id"]
            first = check_controlled_answer(
                workspace, session_id, 0, ["the speaker"]
            )
            second = check_controlled_answer(
                workspace, session_id, 0, ["Luca"]
            )

        self.assertEqual(first["rule_en"], "")
        self.assertIn("Luca", second["rule_en"])
        self.assertEqual(second["answers"], ["Luca"])


class ScenarioConversationTests(unittest.TestCase):
    def test_scenario_catalog_is_public_and_safe(self):
        scenarios = list_conversation_scenarios()

        self.assertTrue(scenarios)
        for scenario in scenarios:
            self.assertIn("key", scenario)
            self.assertIn("level", scenario)
            # The opening line is added later, per session, by the server.
            self.assertNotIn("opening_it", scenario)

    def test_scenario_is_stored_and_reused_across_turns(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            session_id = session["session_id"]
            context = session_conversation_context(
                workspace, session_id, scenario_key="dal_medico"
            )
            follow_up = session_conversation_context(workspace, session_id)

        self.assertEqual(context["opening_it"], "Si accomodi. Che cosa la preoccupa?")
        self.assertEqual(follow_up["scenario_en"], context["scenario_en"])

    def test_unknown_scenario_is_rejected(self):
        fake = FakeGrammarAnki(input_card(), input_deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)

            with self.assertRaisesRegex(ValueError, "Unknown conversation scenario"):
                session_conversation_context(
                    workspace, session["session_id"], scenario_key="nonesuch"
                )


if __name__ == "__main__":
    unittest.main()
