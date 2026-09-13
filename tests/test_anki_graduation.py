import unittest

from anki_graduation import (
    GRADUATION_MIN_REPS,
    graduation_plan,
    my_sentence_counts,
    run_graduation,
)


class FakeAnki:
    """Minimal AnkiConnect fake: production + recognition cards per note."""

    def __init__(self, notes):
        # notes: list of dicts {note_id, rec_reps, production_suspended}
        self.notes = notes
        self.suspended_calls = []
        self.unsuspended_calls = []
        self.next_card_id = 100
        self.production_ids = []
        self.all_cards = {}
        self.note_records = []
        self._build()

    def _build(self):
        for note in self.notes:
            rec_id = self.next_card_id
            self.next_card_id += 1
            prod_id = self.next_card_id
            self.next_card_id += 1
            self.production_ids.append(prod_id)
            self.all_cards[rec_id] = {
                "cardId": rec_id,
                "note": note["note_id"],
                "order": 0,
                "reps": note["rec_reps"],
                "queue": 0,
            }
            self.all_cards[prod_id] = {
                "cardId": prod_id,
                "note": note["note_id"],
                "order": 1,
                "reps": 0,
                "queue": -1 if note["production_suspended"] else 0,
            }
            self.note_records.append({
                "noteId": note["note_id"],
                "cards": [rec_id, prod_id],
                "fields": {"Back": {"value": note.get("back", "")}},
            })

    def __call__(self, action, params=None):
        params = params or {}
        if action == "findCards":
            if "card:" in params["query"]:
                return list(self.production_ids)
            return []
        if action == "findNotes":
            return [note["note_id"] for note in self.notes]
        if action == "cardsInfo":
            wanted = set(params["cards"])
            return [card for card in self.all_cards.values() if card["cardId"] in wanted]
        if action == "notesInfo":
            wanted = set(params["notes"])
            return [n for n in self.note_records if n["noteId"] in wanted]
        if action == "suspend":
            self.suspended_calls.append(list(params["cards"]))
            return None
        if action == "unsuspend":
            self.unsuspended_calls.append(list(params["cards"]))
            return None
        raise AssertionError(action)


class GraduationPlanTests(unittest.TestCase):
    def test_young_production_card_is_suspended(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": 1, "production_suspended": False},
        ])
        plan = graduation_plan(fake, "Italian")

        self.assertEqual(len(plan["to_suspend"]), 1)
        self.assertEqual(plan["to_release"], [])
        self.assertEqual(plan["to_suspend"][0]["recognition_reps"], 1)

    def test_mature_production_card_is_released(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": GRADUATION_MIN_REPS + 4,
             "production_suspended": True},
        ])
        plan = graduation_plan(fake, "Italian")

        self.assertEqual(len(plan["to_release"]), 1)
        self.assertEqual(plan["to_suspend"], [])
        self.assertEqual(plan["mature"], 1)

    def test_in_place_cards_need_no_changes(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": GRADUATION_MIN_REPS + 1,
             "production_suspended": False},
            {"note_id": 2, "rec_reps": 1, "production_suspended": True},
        ])
        plan = graduation_plan(fake, "Italian")

        self.assertEqual(plan["to_release"], [])
        self.assertEqual(plan["to_suspend"], [])
        self.assertEqual(plan["production_cards"], 2)

    def test_preview_makes_no_state_changing_calls(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": 1, "production_suspended": False},
        ])
        graduation_plan(fake, "Italian")

        self.assertEqual(fake.suspended_calls, [])
        self.assertEqual(fake.unsuspended_calls, [])


class GraduationRunTests(unittest.TestCase):
    def test_apply_suspends_and_releases(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": 1, "production_suspended": False},
            {"note_id": 2, "rec_reps": 10, "production_suspended": True},
        ])
        result = run_graduation(fake, "Italian", apply=True)

        self.assertTrue(result["applied"])
        self.assertEqual(len(fake.suspended_calls), 1)
        self.assertEqual(len(fake.unsuspended_calls), 1)
        self.assertEqual(result["released"], 1)
        self.assertEqual(result["suspended"], 1)

    def test_preview_does_not_apply(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": 1, "production_suspended": False},
        ])
        result = run_graduation(fake, "Italian", apply=False)

        self.assertFalse(result["applied"])
        self.assertEqual(fake.suspended_calls, [])


class MySentenceCountsTests(unittest.TestCase):
    def test_counts_personalized_vs_placeholder_notes(self):
        fake = FakeAnki([
            {"note_id": 1, "rec_reps": 0, "production_suspended": False,
             "back": "<div>My sentence</div><div>Edit this note in Anki and replace this line with one sentence.</div>"},
            {"note_id": 2, "rec_reps": 0, "production_suspended": False,
             "back": "<div>My sentence</div><div>Ogni sera leggo un libro in italiano.</div>"},
        ])
        counts = my_sentence_counts(fake, "Italian")

        self.assertEqual(counts["notes"], 2)
        self.assertEqual(counts["with_placeholder"], 1)
        self.assertEqual(counts["personalized"], 1)


if __name__ == "__main__":
    unittest.main()
