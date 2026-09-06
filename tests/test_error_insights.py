import tempfile
import unittest
from pathlib import Path

from error_insights import collect_errors, recommend_topics
from grammar_practice import (
    anki_metadata_fields,
    check_controlled_answer,
    create_session,
)


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
        self.cards = [{"cardId": 11, "note": 1, "reps": 0, "lapses": 0}]

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


STANDARD_CARD = {
    "card_id": "gli",
    "mode": "standard",
    "target_form": "gli",
    "front_html": "<div>Marco _____ parla.</div>",
    "back_html": "<div>gli</div>",
}
STANDARD_DECK = {
    "mode": "standard",
    "topic": "Pronomi indiretti",
    "_topic_key": "pronomi_indiretti",
    "level": "A2",
}

CATALOGS = {
    "standard": {
        "pronomi_indiretti": {
            "title_it": "Pronomi indiretti",
            "title_en": "Indirect pronouns",
            "level": "A2",
            "prompt_hint": "gli, le, mi, ti, ci, vi",
        },
        "articoli_determinativi": {
            "title_it": "Articoli determinativi",
            "title_en": "Definite Articles",
            "level": "A1",
            "prompt_hint": "il, lo, la, l', i, gli, le",
        },
        "passato_prossimo": {
            "title_it": "Passato prossimo",
            "title_en": "Present Perfect",
            "level": "A2",
            "prompt_hint": "essere/avere auxiliaries and participles",
        },
    },
}


class CollectErrorsTests(unittest.TestCase):
    def test_merges_all_three_practice_stores(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fake = FakeGrammarAnki(STANDARD_CARD, STANDARD_DECK)
            session = create_session(fake, workspace, count=1)
            check_controlled_answer(
                workspace, session["session_id"], 0, ["lo"]
            )
            (workspace / ".anki-generator" / "learning-lab").mkdir(parents=True)
            (workspace / ".anki-generator" / "learning-lab" / "state-v1.json").write_text(
                '{"schema": "anki-generator-learning-lab-v1", "error_memory": {'
                '"verb_conjugation": {"category": "verb_conjugation", "count": 3, '
                '"learner_fragment": "Io sono mangiato", "corrected_fragment": '
                '"Ho mangiato", "explanation_en": "Auxiliary choice", '
                '"updated_at": "2026-09-01T10:00:00+00:00"}}}'
            )
            (workspace / ".anki-generator" / "practice").mkdir(parents=True)
            (workspace / ".anki-generator" / "practice" / "state-v1.json").write_text(
                '{"schema": "anki-generator-practice-state-v1", "mistakes": {'
                '"mangiare|tense_mood": {"word": "mangiare", "error_type": '
                '"tense_mood", "count": 2, "last_seen": '
                '"2026-09-02T10:00:00+00:00"}}}'
            )

            result = collect_errors(workspace)

        sources = {entry["source"] for entry in result["patterns"]}
        self.assertEqual(
            sources, {"grammar_practice", "speaking_lab", "word_practice"}
        )
        self.assertEqual(result["total_errors"], 6)
        self.assertEqual(result["top"][0]["label"], "verb conjugation")

    def test_broken_or_missing_states_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / ".anki-generator" / "learning-lab").mkdir(parents=True)
            (workspace / ".anki-generator" / "learning-lab" / "state-v1.json").write_text(
                "{not json"
            )

            result = collect_errors(workspace)

        self.assertEqual(result["patterns"], [])
        self.assertEqual(result["total_errors"], 0)


class RecommendTopicsTests(unittest.TestCase):
    def test_pronoun_errors_reach_pronoun_topics(self):
        patterns = [{
            "source": "grammar_practice",
            "error_type": "pronoun",
            "label": "Pronomi indiretti",
            "count": 4,
            "last_seen": "2026-09-04T00:00:00+00:00",
            "sample": "lo ho dato",
        }]

        recommendations = recommend_topics(patterns, CATALOGS)

        self.assertTrue(recommendations)
        self.assertEqual(recommendations[0]["topic_key"], "pronomi_indiretti")

    def test_mastered_topics_are_not_recommended(self):
        patterns = [{
            "source": "grammar_practice",
            "error_type": "pronoun",
            "label": "Pronomi indiretti",
            "count": 4,
            "last_seen": "2026-09-04T00:00:00+00:00",
        }]

        recommendations = recommend_topics(
            patterns,
            CATALOGS,
            mastery={"pronomi_indiretti": {"status": "mastered"}},
        )

        self.assertEqual(
            [entry["topic_key"] for entry in recommendations],
            [],
        )

    def test_one_recommendation_per_error_family(self):
        patterns = [
            {
                "source": "grammar_practice",
                "error_type": "pronoun",
                "label": "Pronomi indiretti",
                "count": 3,
                "last_seen": "2026-09-04T00:00:00+00:00",
            },
            {
                "source": "speaking_lab",
                "error_type": "article",
                "label": "article before consonant",
                "count": 2,
                "last_seen": "2026-09-03T00:00:00+00:00",
            },
        ]

        recommendations = recommend_topics(patterns, CATALOGS, limit=3)

        families = [entry["error_type"] for entry in recommendations]
        self.assertEqual(len(families), len(set(families)))


if __name__ == "__main__":
    unittest.main()
