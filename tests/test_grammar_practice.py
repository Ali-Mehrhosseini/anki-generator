import json
import tempfile
import unittest
from pathlib import Path

from grammar_practice import (
    anki_metadata_fields,
    backfill_legacy_metadata,
    check_controlled_answer,
    create_session,
    load_state,
    mastery_by_topic,
    practice_overview,
    practice_payload_for_card,
    record_conversation_result,
    record_transfer_result,
    select_interleaved_items,
    session_summary,
)
from main import validate_grammar_card_set


def standard_card(card_id="gli", target="gli"):
    return {
        "card_id": card_id,
        "mode": "standard",
        "target_form": target,
        "accepted_answers": [target.capitalize()],
        "front_html": "<div>Ho telefonato a Marco e _____ ho parlato.</div>",
        "back_html": f"<div>{target}</div>",
        "rule_explanation_en": "Use an indirect pronoun with parlare a.",
        "rule_explanation_fa": "با parlare a از ضمیر غیرمستقیم استفاده کنید.",
    }


def deck(topic="Pronomi indiretti", key="pronomi_indiretti"):
    return {
        "mode": "standard",
        "topic": topic,
        "_topic_key": key,
        "level": "A2",
    }


class FakeGrammarAnki:
    def __init__(self):
        self.notes = []
        self.cards = []

    def add(self, note_id, card_id, card, card_deck, **review):
        metadata = anki_metadata_fields(card, card_deck, 1)
        self.notes.append({
            "noteId": note_id,
            "cards": [card_id],
            "fields": {
                name: {"value": value}
                for name, value in metadata.items()
            },
        })
        self.cards.append({
            "cardId": card_id,
            "note": note_id,
            "reps": review.get("reps", 0),
            "lapses": review.get("lapses", 0),
            "interval": review.get("interval", 0),
            "factor": review.get("factor", 2500),
        })

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
        if action == "updateNoteFields":
            target = next(
                note for note in self.notes
                if note["noteId"] == params["note"]["id"]
            )
            for name, value in params["note"]["fields"].items():
                target["fields"][name] = {"value": value}
            return None
        raise AssertionError(action)


class GrammarMetadataTests(unittest.TestCase):
    def test_saved_metadata_contains_machine_gradable_answer(self):
        fields = anki_metadata_fields(standard_card(), deck(), 1)
        payload = json.loads(fields["AG_PracticeData"])

        self.assertEqual(fields["AG_Answer"], "gli")
        self.assertEqual(payload["topic_key"], "pronomi_indiretti")
        self.assertEqual(payload["answers"], ["gli"])
        self.assertNotIn("answers", {
            key: payload[key]
            for key in ("mode", "topic", "front_html")
        })

    def test_validator_rejects_missing_machine_answer(self):
        cards = [standard_card(str(index), target="") for index in range(4)]
        data = {"cards": cards}

        with self.assertRaisesRegex(ValueError, "missing its answer"):
            validate_grammar_card_set(data, "standard")


class AdaptiveGrammarTests(unittest.TestCase):
    def test_legacy_standard_card_is_migrated_without_guessing_contrast(self):
        fake = FakeGrammarAnki()
        fake.notes = [{
            "noteId": 1,
            "cards": [11],
            "fields": {
                "Topic": {"value": "Pronomi indiretti — gli"},
                "Front": {"value": "<div>Marco _____ parla.</div>"},
                "Back": {"value": "<div>gli</div>"},
                "Level": {"value": "A2"},
            },
        }]
        fake.cards = [{"cardId": 11, "note": 1}]

        result = backfill_legacy_metadata(
            fake,
            lambda topic, mode: ("pronomi_indiretti", {"title_it": topic}),
        )

        self.assertEqual(result["migrated"], [1])
        payload = json.loads(fake.notes[0]["fields"]["AG_PracticeData"]["value"])
        self.assertEqual(payload["answers"], ["gli"])

    def test_interleaving_avoids_adjacent_topics_when_possible(self):
        items = [
            {"topic_key": "a", "strength": 1},
            {"topic_key": "a", "strength": 2},
            {"topic_key": "b", "strength": 3},
            {"topic_key": "c", "strength": 4},
        ]
        chosen = select_interleaved_items(items, {"recent_topics": []}, count=4)

        self.assertTrue(all(
            chosen[index]["topic_key"] != chosen[index - 1]["topic_key"]
            for index in range(1, len(chosen))
        ))

    def test_wrong_answer_requires_retry_before_reveal(self):
        fake = FakeGrammarAnki()
        fake.add(1, 11, standard_card(), deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            first = check_controlled_answer(
                workspace, session["session_id"], 0, ["lo"]
            )
            second = check_controlled_answer(
                workspace, session["session_id"], 0, ["gli"]
            )

            self.assertTrue(first["retry_required"])
            self.assertEqual(first["answers"], [])
            self.assertTrue(second["correct"])
            self.assertEqual(second["answers"], ["gli"])
            stats = load_state(workspace)["topic_stats"]["pronomi_indiretti"]
            self.assertEqual(stats["controlled_attempts"], 2)
            self.assertEqual(stats["controlled_eventual_correct"], 1)

    def test_mastery_uses_review_and_local_practice_evidence(self):
        fake = FakeGrammarAnki()
        fake.add(
            1, 11, standard_card(), deck(),
            reps=20, lapses=0, interval=30, factor=2500,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = mastery_by_topic(fake, Path(directory))

        self.assertGreaterEqual(result["pronomi_indiretti"]["score"], 60)
        self.assertEqual(result["pronomi_indiretti"]["status"], "transfer-ready")
        self.assertGreaterEqual(
            result["pronomi_indiretti"]["stages"]["recognition"], 90
        )

    def test_error_notebook_classifies_controlled_misses(self):
        fake = FakeGrammarAnki()
        fake.add(1, 11, standard_card(), deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            check_controlled_answer(
                workspace, session["session_id"], 0, ["lo"]
            )
            errors = load_state(workspace)["error_notebook"]

        entry = next(iter(errors.values()))
        self.assertEqual(entry["error_type"], "pronoun")
        self.assertEqual(entry["stage"], "controlled")
        self.assertEqual(entry["count"], 1)

    def test_free_and_speaking_evidence_stay_separate(self):
        fake = FakeGrammarAnki()
        fake.add(1, 11, standard_card(), deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            session_id = session["session_id"]
            free = record_transfer_result(
                workspace,
                session_id,
                "Gli ho parlato.",
                {"correct": True, "error_type": "none"},
                stage="free",
            )
            speaking = record_transfer_result(
                workspace,
                session_id,
                "Gli ho parlato ieri.",
                {"correct": True, "error_type": "none"},
                stage="speaking",
            )
            stats = load_state(workspace)["topic_stats"]["pronomi_indiretti"]

        self.assertEqual(free["attempt_number"], 1)
        self.assertEqual(speaking["attempt_number"], 1)
        self.assertEqual(stats["transfer_attempts"], 1)
        self.assertEqual(stats["speaking_attempts"], 1)

    def test_conversation_and_summary_are_recorded(self):
        fake = FakeGrammarAnki()
        fake.add(1, 11, standard_card(), deck())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            session = create_session(fake, workspace, count=1)
            session_id = session["session_id"]
            check_controlled_answer(workspace, session_id, 0, ["gli"])
            record_conversation_result(
                workspace,
                session_id,
                "Gli ho parlato ieri.",
                {"correct": True, "error_type": "none", "reply_it": "Bene!"},
            )
            summary = session_summary(workspace, session_id)

        self.assertEqual(summary["controlled_items"], 1)
        self.assertEqual(summary["first_try_correct"], 1)
        self.assertEqual(summary["conversation_turns"], 1)

    def test_today_overview_exposes_five_stage_averages(self):
        fake = FakeGrammarAnki()
        fake.add(1, 11, standard_card(), deck())
        with tempfile.TemporaryDirectory() as directory:
            overview = practice_overview(fake, Path(directory))

        self.assertEqual(overview["recommended_cards"], 1)
        self.assertEqual(
            set(overview["stage_averages"]),
            {"recognition", "input", "controlled", "free", "speaking"},
        )


if __name__ == "__main__":
    unittest.main()
