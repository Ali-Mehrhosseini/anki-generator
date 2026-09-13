"""Automatic card graduation: recognition first, production when mature.

Research on flashcard retrieval formats shows production cards stick better
but cost roughly twice the review time, so the evidence-backed sequence is
recognition first and production only once the card is young-but-mature.
The production content already lives in the note's AG_ fields, so
graduation is purely Anki card suspension state — scheduling authority
(Anki/FSRS) is never touched directly.
"""
from __future__ import annotations

from collections import defaultdict

PRODUCTION_TEMPLATE_NAME = "AG Production Recall"
GRADUATION_MIN_REPS = 3
_CHUNK = 500


def _chunks(values, size=_CHUNK):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _cards_by_id(invoke_anki, card_ids):
    cards = []
    for chunk in _chunks(card_ids):
        cards.extend(invoke_anki("cardsInfo", {"cards": chunk}) or [])
    return {int(card["cardId"]): card for card in cards if card}


def graduation_plan(invoke_anki, deck_name: str) -> dict:
    """Preview every suspension change graduation would make. Read-only."""
    deck_query = f'deck:"{deck_name}"'
    production_ids = invoke_anki(
        "findCards", {"query": f'{deck_query} card:"{PRODUCTION_TEMPLATE_NAME}"'}
    ) or []
    production_ids = [int(card_id) for card_id in production_ids]
    if not production_ids:
        return {
            "production_cards": 0,
            "to_suspend": [],
            "to_release": [],
            "mature": 0,
            "immature": 0,
            "notes_without_production": 0,
        }

    production_cards = _cards_by_id(invoke_anki, production_ids)
    note_ids = sorted({int(card["note"]) for card in production_cards.values()})

    # All cards of those notes, so the recognition card (template ordinal 0)
    # can be paired with its production card.
    all_card_ids = []
    for chunk in _chunks(note_ids):
        for note in invoke_anki("notesInfo", {"notes": chunk}) or []:
            all_card_ids.extend(int(card_id) for card_id in (note.get("cards") or []))
    all_cards = _cards_by_id(invoke_anki, all_card_ids)
    cards_by_note = defaultdict(list)
    for card in all_cards.values():
        cards_by_note[int(card["note"])].append(card)

    to_suspend = []
    to_release = []
    mature = 0
    immature = 0
    for prod_id in production_ids:
        prod_card = production_cards.get(prod_id)
        if not prod_card:
            continue
        note_id = int(prod_card["note"])
        siblings = cards_by_note.get(note_id, [])
        recognition = next(
            (card for card in siblings if int(card.get("order") or 0) == 0),
            None,
        )
        if recognition is None:
            continue
        rec_reps = int(recognition.get("reps") or 0)
        suspended = int(prod_card.get("queue") or 0) == -1
        if rec_reps >= GRADUATION_MIN_REPS:
            mature += 1
            if suspended:
                to_release.append({
                    "card_id": prod_id,
                    "note_id": note_id,
                    "recognition_reps": rec_reps,
                })
        else:
            immature += 1
            if not suspended:
                to_suspend.append({
                    "card_id": prod_id,
                    "note_id": note_id,
                    "recognition_reps": rec_reps,
                })

    return {
        "production_cards": len(production_ids),
        "to_suspend": to_suspend,
        "to_release": to_release,
        "mature": mature,
        "immature": immature,
        "graduation_min_reps": GRADUATION_MIN_REPS,
        "notes_without_production": 0,
    }


def run_graduation(invoke_anki, deck_name: str, apply: bool = False) -> dict:
    """Apply the graduation plan: suspend young, release mature."""
    plan = graduation_plan(invoke_anki, deck_name)
    result = {**plan, "applied": bool(apply)}
    if not apply:
        return result
    release_ids = [item["card_id"] for item in plan["to_release"]]
    suspend_ids = [item["card_id"] for item in plan["to_suspend"]]
    if release_ids:
        invoke_anki("unsuspend", {"cards": release_ids})
    if suspend_ids:
        invoke_anki("suspend", {"cards": suspend_ids})
    result["released"] = len(release_ids)
    result["suspended"] = len(suspend_ids)
    return result


def my_sentence_counts(invoke_anki, deck_name: str) -> dict:
    """How many cards still carry the untouched 'My sentence' placeholder.

    The generation effect: notes the learner personally edited (their own
    sentence) are retained better than read-only AI cards. The static
    placeholder line disappears the moment they fill theirs in.
    """
    note_ids = invoke_anki(
        "findNotes", {"query": f'deck:"{deck_name}"'}
    ) or []
    note_ids = [int(note_id) for note_id in note_ids]
    placeholder = "Edit this note in Anki and replace this line"
    total = 0
    with_placeholder = 0
    for chunk in _chunks(note_ids):
        for note in invoke_anki("notesInfo", {"notes": chunk}) or []:
            fields = note.get("fields") or {}
            back = str((fields.get("Back") or {}).get("value") or "")
            total += 1
            if placeholder in back:
                with_placeholder += 1
    return {
        "notes": total,
        "with_placeholder": with_placeholder,
        "personalized": max(0, total - with_placeholder),
    }
