"""Adaptive, interleaved practice for app-owned Italian grammar cards."""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


STATE_SCHEMA = "anki-generator-grammar-practice-v1"
STATE_PATH = Path(".anki-generator", "grammar-practice", "state-v1.json")
GRAMMAR_MODEL_NAME = "Italian Grammar"
GRAMMAR_DECK_NAME = "Italian::Grammar"
METADATA_FIELDS = (
    "AG_Mode",
    "AG_TopicKey",
    "AG_CardID",
    "AG_Answer",
    "AG_Alternatives",
    "AG_PracticeData",
)


def default_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "topic_stats": {},
        "sessions": {},
        "recent_topics": [],
        "error_notebook": {},
        "delayed_tasks": {},
    }


def state_path(workspace: Path) -> Path:
    return workspace.resolve() / STATE_PATH


def load_state(workspace: Path) -> dict:
    path = state_path(workspace)
    if not path.exists():
        return default_state()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "Grammar practice history is unreadable; nothing was changed."
        ) from error
    if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
        raise ValueError("Grammar practice history has an unsupported format.")
    value.setdefault("topic_stats", {})
    value.setdefault("sessions", {})
    value.setdefault("recent_topics", [])
    value.setdefault("error_notebook", {})
    value.setdefault("delayed_tasks", {})
    return value


def save_state(workspace: Path, state: dict) -> Path:
    path = state_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".grammar-practice.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(state, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def _field(note: dict, name: str) -> str:
    return str(((note.get("fields") or {}).get(name) or {}).get("value") or "")


def _chunks(values, size=500):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _normalize_answer(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = value.replace("’", "'")
    value = re.sub(r"\s+", " ", value).strip()
    return value.rstrip(" .!?;:")


def practice_payload_for_card(card: dict, deck: dict, index: int) -> dict:
    """Create stable, machine-readable practice metadata for one saved card."""
    mode = str(deck.get("mode") or card.get("mode") or "standard")
    topic = str(deck.get("topic") or "Grammar").strip()
    topic_key = str(deck.get("_topic_key") or "").strip()
    card_id = str(card.get("card_id") or f"card_{index}").strip()

    if mode == "contrast":
        answers = [
            str(card.get("sentence_a_target") or "").strip(),
            str(card.get("sentence_b_target") or "").strip(),
        ]
        accepted = []
        rule_en = str(card.get("contrast_rule_en") or "").strip()
        rule_fa = str(card.get("contrast_rule_fa") or "").strip()
    elif mode == "mistake":
        answers = [str(card.get("corrected_sentence") or "").strip()]
        accepted = []
        rule_en = str(card.get("why_error_en") or "").strip()
        rule_fa = str(card.get("why_error_fa") or "").strip()
    elif mode == "input":
        options = [
            str(option).strip()
            for option in (card.get("answer_options") or [])
            if str(option).strip()
        ]
        try:
            answer_index = int(card.get("answer_index"))
        except (TypeError, ValueError):
            answer_index = -1
        if not options or not 0 <= answer_index < len(options):
            raise ValueError(
                f"Grammar card {card_id} is missing its correct interpretation."
            )
        answers = [options[answer_index]]
        accepted = []
        rule_en = str(card.get("form_meaning_en") or "").strip()
        rule_fa = str(card.get("form_meaning_fa") or "").strip()
    else:
        mode = "standard"
        answers = [str(card.get("target_form") or "").strip()]
        accepted = [
            str(item).strip()
            for item in (card.get("accepted_answers") or [])
            if str(item).strip()
        ]
        rule_en = str(card.get("rule_explanation_en") or "").strip()
        rule_fa = str(card.get("rule_explanation_fa") or "").strip()

    if not all(answers):
        raise ValueError(f"Grammar card {card_id} is missing its expected answer.")

    payload = {
        "version": 1,
        "mode": mode,
        "topic": topic,
        "topic_key": topic_key,
        "level": str(deck.get("level") or "A1"),
        "card_id": card_id,
        "front_html": str(card.get("front_html") or "").strip(),
        "answers": answers,
        "accepted_answers": accepted,
        "rule_en": rule_en,
        "rule_fa": rule_fa,
        "back_html": str(card.get("back_html") or "").strip(),
    }
    if mode == "input":
        payload["answer_options"] = options
    return payload


def anki_metadata_fields(card: dict, deck: dict, index: int) -> dict:
    payload = practice_payload_for_card(card, deck, index)
    return {
        "AG_Mode": payload["mode"],
        "AG_TopicKey": payload["topic_key"],
        "AG_CardID": payload["card_id"],
        "AG_Answer": " || ".join(payload["answers"]),
        "AG_Alternatives": json.dumps(
            payload["accepted_answers"], ensure_ascii=False
        ),
        "AG_PracticeData": json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ),
    }


def _card_strength(card: dict) -> float:
    reps = max(0, int(card.get("reps") or 0))
    lapses = max(0, int(card.get("lapses") or 0))
    interval = max(0, int(card.get("interval") or 0))
    factor = max(0, int(card.get("factor") or 0))
    if reps == 0:
        return 0.0
    accuracy = max(0.0, 1.0 - lapses / max(reps, 1))
    return min(100.0, accuracy * 55 + min(interval, 30) + min(factor, 2500) / 250)


def discover_practice_items(invoke_anki) -> list[dict]:
    """Read metadata and review history for adaptive grammar practice."""
    note_ids = invoke_anki(
        "findNotes",
        {"query": f'deck:"{GRAMMAR_DECK_NAME}" note:"{GRAMMAR_MODEL_NAME}"'},
    ) or []
    notes = []
    for chunk in _chunks(note_ids):
        notes.extend(invoke_anki("notesInfo", {"notes": chunk}) or [])
    card_ids = [
        int(card_id)
        for note in notes
        for card_id in (note.get("cards") or [])
    ]
    cards = []
    for chunk in _chunks(card_ids):
        cards.extend(invoke_anki("cardsInfo", {"cards": chunk}) or [])
    cards_by_note = {
        int(card.get("note") or 0): card
        for card in cards
        if card
    }

    items = []
    for note in notes:
        raw = _field(note, "AG_PracticeData")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("version") != 1:
            continue
        note_id = int(note.get("noteId") or 0)
        card = cards_by_note.get(note_id, {})
        item = dict(payload)
        item.update({
            "note_id": note_id,
            "card_id_anki": int(card.get("cardId") or 0),
            "reps": int(card.get("reps") or 0),
            "lapses": int(card.get("lapses") or 0),
            "interval": int(card.get("interval") or 0),
            "due": int(card.get("due") or 0),
            "queue": int(card.get("queue") or 0),
            "strength": _card_strength(card),
        })
        items.append(item)
    return items


def backfill_legacy_metadata(invoke_anki, resolve_topic) -> dict:
    """Add metadata only when a legacy answer can be inferred unambiguously."""
    note_ids = invoke_anki(
        "findNotes",
        {"query": f'deck:"{GRAMMAR_DECK_NAME}" note:"{GRAMMAR_MODEL_NAME}"'},
    ) or []
    notes = []
    for chunk in _chunks(note_ids):
        notes.extend(invoke_anki("notesInfo", {"notes": chunk}) or [])
    migrated = []
    skipped = []
    corrected_pattern = re.compile(r">\s*✅\s*([^<]+)</div>", re.IGNORECASE)

    for note in notes:
        note_id = int(note.get("noteId") or 0)
        if _field(note, "AG_PracticeData").strip():
            continue
        topic_field = _field(note, "Topic").strip()
        front_html = _field(note, "Front")
        back_html = _field(note, "Back")
        if " — " not in topic_field or not front_html or not back_html:
            skipped.append(note_id)
            continue
        topic_name, suffix = topic_field.rsplit(" — ", 1)
        if "Contrast Challenge" in front_html:
            # A pair label does not reliably reveal the inflected answers.
            skipped.append(note_id)
            continue
        if "Trova l'Errore" in front_html:
            mode = "mistake"
            match = corrected_pattern.search(back_html)
            answer = html.unescape(match.group(1)).strip() if match else ""
            card = {
                "card_id": f"legacy_{note_id}",
                "mode": mode,
                "corrected_sentence": answer,
                "front_html": front_html,
                "back_html": back_html,
            }
        elif "_____" in front_html and suffix.strip():
            mode = "standard"
            card = {
                "card_id": f"legacy_{note_id}",
                "mode": mode,
                "target_form": suffix.strip(),
                "front_html": front_html,
                "back_html": back_html,
            }
        else:
            skipped.append(note_id)
            continue
        missing_legacy_answer = (
            not answer if mode == "mistake" else not suffix.strip()
        )
        if missing_legacy_answer:
            skipped.append(note_id)
            continue
        topic_key, topic_info = resolve_topic(topic_name, mode=mode)
        deck = {
            "mode": mode,
            "topic": (
                topic_info.get("title_it")
                if isinstance(topic_info, dict) else topic_name
            ),
            "_topic_key": topic_key or "",
            "level": _field(note, "Level") or "A1",
        }
        fields = anki_metadata_fields(card, deck, 1)
        invoke_anki(
            "updateNoteFields",
            {"note": {"id": note_id, "fields": fields}},
        )
        migrated.append(note_id)
    return {"migrated": migrated, "skipped": skipped}


def select_interleaved_items(
    items: list[dict],
    state: dict,
    *,
    count: int = 6,
    priority_topic_keys: set[str] | None = None,
) -> list[dict]:
    """Prefer weak items while avoiding same-topic runs where possible."""
    if count < 1:
        raise ValueError("Grammar practice count must be at least one.")
    recent = {
        str(value)
        for value in (state.get("recent_topics") or [])[-4:]
    }
    ranked = sorted(
        items,
        key=lambda item: (
            0 if str(item.get("topic_key") or "") in (priority_topic_keys or set()) else 1,
            float(item.get("strength") or 0),
            str(item.get("topic_key") or item.get("topic") or ""),
        ),
    )
    unseen_recent = [
        item for item in ranked
        if str(item.get("topic_key") or item.get("topic")) not in recent
    ]
    pool = unseen_recent + [item for item in ranked if item not in unseen_recent]
    chosen = []
    remaining = list(pool)
    last_topic = None
    while remaining and len(chosen) < count:
        index = next((
            idx for idx, item in enumerate(remaining)
            if str(item.get("topic_key") or item.get("topic")) != last_topic
        ), 0)
        item = remaining.pop(index)
        chosen.append(item)
        last_topic = str(item.get("topic_key") or item.get("topic"))
    return chosen


def _public_item(item: dict) -> dict:
    keys = (
        "mode", "topic", "topic_key", "level", "card_id",
        "front_html", "note_id", "strength", "reps", "lapses",
        "interval",
    )
    if item.get("mode") == "input":
        # Interpretations are visible choices; the correct one stays server-side.
        keys = keys + ("answer_options",)
    return {
        key: item.get(key)
        for key in keys
    } | {"input_count": 2 if item.get("mode") == "contrast" else 1}


def _transfer_prompt(items: list[dict]) -> dict:
    distinct = []
    seen = set()
    for item in items:
        identity = str(item.get("topic_key") or item.get("topic"))
        if identity in seen:
            continue
        seen.add(identity)
        distinct.append(item)
        if len(distinct) == 2:
            break
    labels = [str(item.get("topic") or "grammar target") for item in distinct]
    joined = " and ".join(labels)
    return {
        "topics": [
            {
                "topic_key": item.get("topic_key"),
                "topic": item.get("topic"),
                "rule_en": item.get("rule_en"),
                "rule_fa": item.get("rule_fa"),
            }
            for item in distinct
        ],
        "prompt_en": (
            "Write 2–4 natural Italian sentences about a real situation. "
            f"Demonstrate {joined}. Do not copy the practice examples."
        ),
        "prompt_fa": (
            "۲ تا ۴ جملهٔ طبیعی ایتالیایی دربارهٔ یک موقعیت واقعی بنویس و "
            f"کاربرد {joined} را نشان بده. مثال‌های تمرین را کپی نکن."
        ),
    }


def create_session(
    invoke_anki, workspace: Path, *, count: int = 6
) -> dict:
    state = load_state(workspace)
    items = discover_practice_items(invoke_anki)
    now = datetime.now(timezone.utc)
    due_topic_keys = set()
    for task in (state.get("delayed_tasks") or {}).values():
        try:
            due_at = datetime.fromisoformat(str(task.get("due_at") or ""))
        except ValueError:
            continue
        if due_at <= now:
            due_topic_keys.add(str(task.get("topic_key") or ""))
    selected = select_interleaved_items(
        items,
        state,
        count=count,
        priority_topic_keys=due_topic_keys,
    )
    if not selected:
        return {
            "session_id": None,
            "items": [],
            "transfer": None,
            "message": (
                "No adaptive grammar cards are available yet. Generate and "
                "save new Grammar Deck cards first."
            ),
        }
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    state["sessions"][session_id] = {
        "created_at": now,
        "items": selected,
        "attempts": {},
        "transfer_attempts": [],
    }
    # Bound local state without relying on lexical UUID order.
    ordered = sorted(
        state["sessions"].items(),
        key=lambda pair: str(pair[1].get("created_at") or ""),
    )
    state["sessions"] = dict(ordered[-20:])
    save_state(workspace, state)
    return {
        "session_id": session_id,
        "items": [_public_item(item) for item in selected],
        "transfer": _transfer_prompt(selected),
    }


def _response_matches(item: dict, responses: list[str]) -> bool:
    answers = [
        _normalize_answer(value)
        for value in (item.get("answers") or [])
    ]
    supplied = [_normalize_answer(value) for value in responses]
    if item.get("mode") == "contrast":
        return supplied == answers
    if not supplied:
        return False
    accepted = {
        answers[0],
        *(
            _normalize_answer(value)
            for value in (item.get("accepted_answers") or [])
        ),
    }
    return supplied[0] in accepted


def _topic_stats(state: dict, item: dict) -> dict:
    key = str(item.get("topic_key") or item.get("topic") or "unknown")
    defaults = {
        "topic": item.get("topic"),
        "input_attempts": 0,
        "input_first_try_correct": 0,
        "controlled_attempts": 0,
        "controlled_first_try_correct": 0,
        "controlled_eventual_correct": 0,
        "dictogloss_attempts": 0,
        "dictogloss_correct": 0,
        "transfer_attempts": 0,
        "transfer_correct": 0,
        "speaking_attempts": 0,
        "speaking_correct": 0,
        "conversation_attempts": 0,
        "conversation_correct": 0,
    }
    stats = state.setdefault("topic_stats", {}).setdefault(key, {})
    for field, value in defaults.items():
        stats.setdefault(field, value)
    return stats


def _error_type_for_item(item: dict) -> str:
    """Infer a useful grammar category for a deterministic card miss."""
    identity = " ".join((
        str(item.get("topic_key") or ""),
        str(item.get("topic") or ""),
    )).casefold()
    if item.get("mode") == "mistake":
        return "sentence_correction"
    checks = (
        (("articol",), "article"),
        (("accord", "genere", "aggettiv"), "agreement"),
        (("pronom",), "pronoun"),
        (("prepos",), "preposition"),
        (("passato", "imperfetto", "futuro", "condizional", "congiuntiv", "trapassato"), "tense_mood"),
        (("ordine", "word_order"), "word_order"),
    )
    for needles, label in checks:
        if any(needle in identity for needle in needles):
            return label
    return "grammar_form"


def _record_error(
    state: dict,
    item: dict,
    error_type: str,
    response: str,
    *,
    stage: str,
) -> None:
    topic_key = str(item.get("topic_key") or item.get("topic") or "unknown")
    normalized_type = str(error_type or "other").strip() or "other"
    identity = f"{topic_key}::{normalized_type}::{stage}"
    now = datetime.now(timezone.utc).isoformat()
    entry = state.setdefault("error_notebook", {}).setdefault(identity, {
        "topic_key": topic_key,
        "topic": item.get("topic") or topic_key,
        "error_type": normalized_type,
        "stage": stage,
        "count": 0,
        "first_seen": now,
    })
    entry["count"] = int(entry.get("count") or 0) + 1
    entry["last_seen"] = now
    entry["last_response"] = str(response or "")[:500]


def _schedule_delayed_task(
    state: dict,
    item: dict,
    *,
    stage: str,
    correct: bool,
) -> None:
    topic_key = str(item.get("topic_key") or item.get("topic") or "unknown")
    delay_days = {
        "free": 3 if correct else 1,
        "speaking": 7 if correct else 2,
        "conversation": 4 if correct else 1,
    }.get(stage, 1)
    due_at = datetime.now(timezone.utc) + timedelta(days=delay_days)
    state.setdefault("delayed_tasks", {})[f"{topic_key}::{stage}"] = {
        "topic_key": topic_key,
        "topic": item.get("topic") or topic_key,
        "stage": stage,
        "due_at": due_at.isoformat(),
        "reason": "consolidate" if correct else "repair",
    }


def check_controlled_answer(
    workspace: Path,
    session_id: str,
    item_index: int,
    responses: list[str],
) -> dict:
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    items = session.get("items") or []
    if item_index < 0 or item_index >= len(items):
        raise ValueError("The grammar practice item is invalid.")
    item = items[item_index]
    attempt_key = str(item_index)
    # Interpretation items train a separate comprehension stage.
    stage = "input" if item.get("mode") == "input" else "controlled"
    prior = list((session.get("attempts") or {}).get(attempt_key) or [])
    attempt_number = len(prior) + 1
    correct = _response_matches(item, responses)
    prior.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "responses": [str(value)[:1000] for value in responses],
        "correct": correct,
        "stage": stage,
    })
    session.setdefault("attempts", {})[attempt_key] = prior
    stats = _topic_stats(state, item)
    stats[f"{stage}_attempts"] += 1
    if correct and attempt_number == 1:
        stats[f"{stage}_first_try_correct"] += 1
    if correct and stage == "controlled":
        stats["controlled_eventual_correct"] += 1
    stats["last_seen"] = datetime.now(timezone.utc).isoformat()
    if not correct:
        _record_error(
            state,
            item,
            _error_type_for_item(item),
            " | ".join(str(value) for value in responses),
            stage=stage,
        )

    topic_identity = str(item.get("topic_key") or item.get("topic"))
    recent = list(state.get("recent_topics") or [])
    recent.append(topic_identity)
    state["recent_topics"] = recent[-20:]
    save_state(workspace, state)

    reveal = correct or attempt_number >= 2
    # For interpretation items the form→meaning rule IS the answer, so it
    # stays confidential until the reveal like the answer itself.
    show_rule = reveal or item.get("mode") != "input"
    return {
        "correct": correct,
        "attempt": attempt_number,
        "retry_required": not correct and attempt_number < 2,
        "can_continue": reveal,
        "feedback_en": (
            "Correct—now notice why this form expresses the intended meaning."
            if correct else (
                "Not yet. Read the focused rule and try the same item once more."
                if not reveal else
                "The second attempt is still incorrect. Compare your response with the model answer, then continue."
            )
        ),
        "feedback_fa": (
            "درست است؛ حالا دقت کن چرا این فرم معنای موردنظر را می‌رساند."
            if correct else (
                "هنوز درست نیست. قانون کوتاه را بخوان و همین مورد را یک بار دیگر امتحان کن."
                if not reveal else
                "پاسخ دوم هم درست نبود. پاسخ خود را با جواب الگو مقایسه کن و سپس ادامه بده."
            )
        ),
        "rule_en": (item.get("rule_en") or "") if show_rule else "",
        "rule_fa": (item.get("rule_fa") or "") if show_rule else "",
        "answers": item.get("answers") if reveal else [],
        "back_html": item.get("back_html") if reveal else "",
    }


def session_transfer_context(workspace: Path, session_id: str) -> dict:
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    return _transfer_prompt(session.get("items") or [])


def record_transfer_result(
    workspace: Path,
    session_id: str,
    response: str,
    feedback: dict,
    *,
    stage: str = "free",
) -> dict:
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    feedback = dict(feedback)
    correct = bool(feedback.get("correct"))
    feedback.setdefault("can_continue", correct)
    feedback.setdefault("retry_required", not correct)
    attempt = {
        "at": datetime.now(timezone.utc).isoformat(),
        "response": str(response)[:4000],
        "correct": correct,
        "feedback": feedback,
        "stage": stage,
    }
    session.setdefault("transfer_attempts", []).append(attempt)
    attempt["attempt_number"] = sum(
        str(item.get("stage") or "free") == stage
        for item in session["transfer_attempts"]
    )
    targets = _transfer_prompt(session.get("items") or [])["topics"]
    for item in targets:
        stats = _topic_stats(state, item)
        if stage == "speaking":
            stats["speaking_attempts"] += 1
            if correct:
                stats["speaking_correct"] += 1
        else:
            stats["transfer_attempts"] += 1
            if correct:
                stats["transfer_correct"] += 1
        stats["last_seen"] = attempt["at"]
        if not correct:
            _record_error(
                state,
                item,
                str(feedback.get("error_type") or "other"),
                response,
                stage=stage,
            )
        _schedule_delayed_task(
            state, item, stage=stage, correct=correct
        )
    save_state(workspace, state)
    return attempt


def record_conversation_result(
    workspace: Path,
    session_id: str,
    response: str,
    feedback: dict,
) -> dict:
    """Record one grammar-controlled dialogue turn."""
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    feedback = dict(feedback)
    correct = bool(feedback.get("correct"))
    feedback.setdefault("can_continue", correct)
    feedback.setdefault("retry_required", not correct)
    now = datetime.now(timezone.utc).isoformat()
    turn = {
        "at": now,
        "response": str(response)[:2000],
        "correct": correct,
        "feedback": feedback,
    }
    turns = session.setdefault("conversation_turns", [])
    turns.append(turn)
    turn["turn_number"] = len(turns)
    for item in _transfer_prompt(session.get("items") or [])["topics"]:
        stats = _topic_stats(state, item)
        stats["conversation_attempts"] += 1
        if correct:
            stats["conversation_correct"] += 1
        else:
            _record_error(
                state,
                item,
                str(feedback.get("error_type") or "other"),
                response,
                stage="conversation",
            )
        stats["last_seen"] = now
        _schedule_delayed_task(
            state, item, stage="conversation", correct=correct
        )
    save_state(workspace, state)
    return turn


CONVERSATION_SCENARIOS = {
    "presentazione": {
        "title_en": "Meeting a classmate",
        "title_it": "Presentarsi a un compagno",
        "title_fa": "آشنایی با یک همکلاسی",
        "level": "A1",
        "scenario_en": (
            "You are introducing yourself to a new Italian classmate before "
            "your first lesson."
        ),
        "scenario_fa": "خودت را قبل از اولین درس به یک همکلاسی ایتالیایی معرفی می‌کنی.",
        "opening_it": "Ciao! Io sono Giulia, e tu come ti chiami?",
        "focus_en": "present tense, subject pronouns, c'è / ci sono",
    },
    "al_mercato": {
        "title_en": "At the market",
        "title_it": "Al mercato",
        "title_fa": "در بازار",
        "level": "A1",
        "scenario_en": (
            "You are buying fruit and cheese at a market stall in Bologna and "
            "the vendor asks what you need."
        ),
        "scenario_fa": "در غرفه‌ای در بولونیا میوه و پنیر می‌خری و فروشنده می‌پرسد چه می‌خواهی.",
        "opening_it": "Buongiorno! Desidera qualcosa?",
        "focus_en": "articles, quantities, simple prepositions",
    },
    "il_weekend": {
        "title_en": "Telling your weekend",
        "title_it": "Raccontare il weekend",
        "title_fa": "تعریف تعطیلات آخر هفته",
        "level": "A2",
        "scenario_en": (
            "You are telling an Italian friend what you did last weekend and "
            "what usually happens on your Sundays."
        ),
        "scenario_fa": "به یک دوست ایتالیایی می‌گویی آخر هفته گذشته چه کردی و یکشنبه‌ها معمولاً چه می‌کنی.",
        "opening_it": "Ciao! Allora, come è andato il fine settimana?",
        "focus_en": "passato prossimo vs imperfetto, reflexive verbs",
    },
    "ricerca_alloggio": {
        "title_en": "Finding a room",
        "title_it": "Cercare una stanza",
        "title_fa": "پیدا کردن اتاق",
        "level": "A2",
        "scenario_en": (
            "You are calling a landlady in Florence about a room advertisement "
            "and asking practical questions."
        ),
        "scenario_fa": "با صاحب‌خانه‌ای در فلورانس دربارهٔ آگهی یک اتاق تلفنی حرف می‌زنی و سؤال‌های عملی می‌پرسی.",
        "opening_it": "Pronto, lei chiama per la stanza, vero?",
        "focus_en": "preposizioni articolate, ne / ci, question forms",
    },
    "dal_medico": {
        "title_en": "At the doctor",
        "title_it": "Dal medico",
        "title_fa": "نزد پزشک",
        "level": "B1",
        "scenario_en": (
            "You are describing symptoms to a doctor and explaining what you "
            "would do if the pain returned."
        ),
        "scenario_fa": "علائم را به پزشک توضیح می‌دهی و می‌گویی اگر درد برگردد چه می‌کنی.",
        "opening_it": "Si accomodi. Che cosa la preoccupa?",
        "focus_en": "condizionale, periodo ipotetico, body vocabulary",
    },
    "progetti_futuri": {
        "title_en": "Plans and dreams",
        "title_it": "Progetti e sogni",
        "title_fa": "برنامه‌ها و رؤیاها",
        "level": "B1",
        "scenario_en": (
            "You are discussing next year's plans with a friend and what you "
            "would change if you could."
        ),
        "scenario_fa": "با دوستی دربارهٔ برنامه‌های سال بعد و اینکه اگر می‌توانستی چه چیزی را تغییر می‌دادی حرف می‌زنی.",
        "opening_it": "Ho letto che vuoi cambiare città. È vero?",
        "focus_en": "futuro semplice, congiuntivo, hypothetical periods",
    },
}


def list_conversation_scenarios() -> list[dict]:
    """Public scenario catalog for the conversation picker."""
    return [
        {
            "key": key,
            "title_en": info["title_en"],
            "title_it": info["title_it"],
            "title_fa": info["title_fa"],
            "level": info["level"],
            "focus_en": info["focus_en"],
        }
        for key, info in CONVERSATION_SCENARIOS.items()
    ]


# Active dictogloss texts. The learner must reconstruct them from audio, so
# the original stays server-side; entries expire with the process.
_DICTOGLOSS_SESSIONS: dict[str, dict] = {}
MAX_DICTOGLOSS_SESSIONS = 20


def create_dictogloss_session(topic: dict, text: dict) -> str:
    session_id = uuid.uuid4().hex
    _DICTOGLOSS_SESSIONS[session_id] = {
        "topic": dict(topic),
        "text_it": str(text.get("text_it") or ""),
        "translation_en": str(text.get("translation_en") or ""),
        "grammar_focus_en": str(text.get("grammar_focus_en") or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "attempts": 0,
    }
    if len(_DICTOGLOSS_SESSIONS) > MAX_DICTOGLOSS_SESSIONS:
        oldest = sorted(
            _DICTOGLOSS_SESSIONS.items(),
            key=lambda pair: pair[1]["created_at"],
        )
        for key, _ in oldest[:len(_DICTOGLOSS_SESSIONS) - MAX_DICTOGLOSS_SESSIONS]:
            _DICTOGLOSS_SESSIONS.pop(key, None)
    return session_id


def dictogloss_session(session_id: str) -> dict | None:
    return _DICTOGLOSS_SESSIONS.get(str(session_id or ""))


def record_dictogloss_result(
    workspace: Path,
    session_id: str,
    response: str,
    feedback: dict,
) -> dict:
    """Record one dictogloss reconstruction against its topic."""
    session = dictogloss_session(session_id)
    if not session:
        raise ValueError("This dictogloss session has expired. Start a new text.")
    state = load_state(workspace)
    topic = session["topic"]
    stats = _topic_stats(state, topic)
    session["attempts"] = int(session.get("attempts") or 0) + 1
    correct = bool(feedback.get("correct"))
    attempt = {
        "at": datetime.now(timezone.utc).isoformat(),
        "response": str(response)[:2000],
        "correct": correct,
        "feedback": dict(feedback),
    }
    (session.setdefault("results", [])).append(attempt)
    stats["dictogloss_attempts"] += 1
    if correct:
        stats["dictogloss_correct"] += 1
    elif session["attempts"] >= 2:
        # The original is the lesson here; schedule a consolidation follow-up.
        _schedule_delayed_task(state, topic, stage="free", correct=False)
    stats["last_seen"] = attempt["at"]
    save_state(workspace, state)
    retry_required = not correct and session["attempts"] < 2
    result = {
        **attempt,
        "attempt_number": session["attempts"],
        "retry_required": retry_required,
    }
    if not retry_required:
        # The original is the lesson — it reveals only after the final
        # attempt, exactly like every other retrieval gate in the app.
        result["text_it"] = session["text_it"]
        result["translation_en"] = session["translation_en"]
        result["grammar_focus_en"] = session["grammar_focus_en"]
    return result


def session_conversation_context(
    workspace: Path, session_id: str, scenario_key: str | None = None
) -> dict:
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    items = session.get("items") or []
    transfer = _transfer_prompt(items)
    level = max((str(item.get("level") or "A1") for item in items), default="A1")
    if scenario_key is not None:
        if scenario_key not in CONVERSATION_SCENARIOS:
            raise ValueError("Unknown conversation scenario.")
        session["scenario_key"] = scenario_key
        save_state(workspace, state)
    else:
        scenario_key = str(session.get("scenario_key") or "")
    scenario = CONVERSATION_SCENARIOS.get(scenario_key)
    if scenario:
        return {
            "level": scenario["level"],
            "scenario_en": scenario["scenario_en"],
            "scenario_fa": scenario["scenario_fa"],
            "opening_it": scenario["opening_it"],
            "topics": transfer["topics"],
            "turns": list(session.get("conversation_turns") or []),
            "max_turns": 3,
        }
    scenarios = {
        "A1": "You are introducing yourself to a new Italian classmate.",
        "A2": "You are telling an Italian friend what happened during your weekend.",
        "B1": "You are discussing a plan and explaining what you would do in that situation.",
    }
    openings = {
        "A1": "Ciao! Come ti chiami e da dove vieni?",
        "A2": "Ciao! Che cosa hai fatto durante il fine settimana?",
        "B1": "Quali sono i tuoi programmi e cosa faresti se avessi più tempo?",
    }
    return {
        "level": level,
        "scenario_en": scenarios.get(level, scenarios["A2"]),
        "scenario_fa": "در یک گفت‌وگوی کوتاه و طبیعی به ایتالیایی پاسخ بده.",
        "opening_it": openings.get(level, openings["A2"]),
        "topics": transfer["topics"],
        "turns": list(session.get("conversation_turns") or []),
        "max_turns": 3,
    }


def session_item_context(
    workspace: Path, session_id: str, item_index: int, responses: list[str]
) -> dict:
    """Build the confidential explanation task for one controlled item."""
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    items = session.get("items") or []
    if item_index < 0 or item_index >= len(items):
        raise ValueError("The grammar practice item is invalid.")
    item = items[item_index]
    is_input = item.get("mode") == "input"
    return {
        "kind": "controlled",
        "mode": str(item.get("mode") or "standard"),
        "level": str(item.get("level") or "A2"),
        "topic": str(item.get("topic") or ""),
        "question_html": str(item.get("front_html") or ""),
        # Input-mode rules name the answer, so they never enter the prompt.
        "rule_en": "" if is_input else str(item.get("rule_en") or ""),
        "rule_fa": "" if is_input else str(item.get("rule_fa") or ""),
        "learner_response": " | ".join(str(value) for value in responses),
    }


def session_summary(workspace: Path, session_id: str) -> dict:
    state = load_state(workspace)
    session = (state.get("sessions") or {}).get(session_id)
    if not session:
        raise ValueError("This grammar practice session has expired.")
    attempts_by_item = session.get("attempts") or {}
    controlled = [
        attempt
        for attempts in attempts_by_item.values()
        for attempt in attempts
        if attempt.get("stage") != "input"
    ]
    input_attempts = [
        attempt
        for attempts in attempts_by_item.values()
        for attempt in attempts
        if attempt.get("stage") == "input"
    ]
    first_attempts = [
        attempts[0]
        for attempts in attempts_by_item.values()
        if attempts
    ]
    first_input = [
        attempts[0]
        for attempts in attempts_by_item.values()
        if attempts and attempts[0].get("stage") == "input"
    ]
    first_controlled = [
        attempts[0]
        for attempts in attempts_by_item.values()
        if attempts and attempts[0].get("stage") != "input"
    ]
    transfer_attempts = session.get("transfer_attempts") or []
    free_attempts = [
        attempt for attempt in transfer_attempts
        if attempt.get("stage") != "speaking"
    ]
    speaking_attempts = [
        attempt for attempt in transfer_attempts
        if attempt.get("stage") == "speaking"
    ]
    conversation_turns = session.get("conversation_turns") or []

    def _percent(correct: int, total: int) -> int:
        return round(correct / total * 100) if total else 0

    # Per-topic outcome with repair candidates for one-tap correction cards.
    # Controlled/input misses belong to the item's own topic; transfer,
    # speaking, and conversation evidence is recorded against every target
    # topic of the session (same attribution as the topic_stats counters).
    free_failures = sum(1 for attempt in free_attempts if not attempt.get("correct"))
    speaking_failures = sum(
        1 for attempt in speaking_attempts if not attempt.get("correct")
    )
    conversation_failures = sum(
        1 for turn in conversation_turns if not turn.get("correct")
    )
    topic_report = []
    repair_candidates = []
    seen = {}
    for item in session.get("items") or []:
        key = str(item.get("topic_key") or item.get("topic"))
        if key in seen:
            continue
        seen[key] = str(item.get("topic") or key)
        item_indices = [
            index
            for index, session_item in enumerate(session.get("items") or [])
            if str(session_item.get("topic_key") or session_item.get("topic")) == key
        ]
        input_misses = sum(
            1 for index in item_indices
            for attempt in attempts_by_item.get(str(index), [])
            if attempt.get("stage") == "input" and not attempt.get("correct")
        )
        controlled_misses = sum(
            1 for index in item_indices
            for attempt in attempts_by_item.get(str(index), [])
            if attempt.get("stage") != "input" and not attempt.get("correct")
        )
        failures = (
            input_misses + controlled_misses + free_failures
            + speaking_failures + conversation_failures
        )
        topic_report.append({
            "topic_key": key,
            "topic": seen[key],
            "mode": str(item.get("mode") or "standard"),
            "input_misses": input_misses,
            "controlled_misses": controlled_misses,
            "transfer_failures": free_failures,
            "speaking_failures": speaking_failures,
            "conversation_failures": conversation_failures,
            "needs_repair": failures > 0,
        })
        if failures:
            repair_candidates.append(key)
    transfer_failures = free_failures

    # Session-scoped error patterns, most frequent first.
    error_patterns = {}
    for index, attempts in attempts_by_item.items():
        item = (session.get("items") or [])[int(index)] if attempts else None
        if item is None:
            continue
        for attempt in attempts:
            if attempt.get("correct") or attempt.get("stage") == "input":
                continue
            error_type = _error_type_for_item(item)
            error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
    for attempt in transfer_attempts:
        if attempt.get("correct"):
            continue
        error_type = str(
            (attempt.get("feedback") or {}).get("error_type") or "other"
        )
        if error_type == "none":
            error_type = "other"
        error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
    for turn in conversation_turns:
        if turn.get("correct"):
            continue
        error_type = str(
            (turn.get("feedback") or {}).get("error_type") or "other"
        )
        if error_type == "none":
            error_type = "other"
        error_patterns[error_type] = error_patterns.get(error_type, 0) + 1

    topics = list(seen)
    topic_labels = {
        str(item.get("topic_key") or item.get("topic")):
            str(item.get("topic") or key)
        for item in (session.get("items") or [])
    }
    session_errors = []
    for entry in (state.get("error_notebook") or {}).values():
        if entry.get("topic") in set(topic_labels.values()):
            session_errors.append(entry)
    session_errors.sort(
        key=lambda entry: (
            -int(entry.get("count") or 0), str(entry.get("error_type") or "")
        )
    )
    return {
        "topics": [
            topic_labels.get(key, key) for key in topics
        ],
        "controlled_items": len(first_controlled),
        "input_items": len(first_input),
        "first_try_correct": sum(
            bool(item.get("correct")) for item in first_controlled
        ),
        "total_controlled_attempts": len(controlled),
        "stage_accuracy": {
            "input": _percent(
                sum(1 for item in first_input if item.get("correct")),
                len(first_input),
            ),
            "controlled": _percent(
                sum(1 for item in first_controlled if item.get("correct")),
                len(first_controlled),
            ),
            "free": _percent(
                sum(1 for attempt in free_attempts if attempt.get("correct")),
                len(free_attempts),
            ),
            "conversation": _percent(
                sum(
                    1 for turn in conversation_turns
                    if (turn.get("feedback") or {}).get("can_continue")
                ),
                len(conversation_turns),
            ),
            "speaking": _percent(
                sum(
                    1 for attempt in speaking_attempts
                    if attempt.get("correct")
                ),
                len(speaking_attempts),
            ),
        },
        "free_attempts": len(free_attempts),
        "conversation_turns": sum(
            bool((turn.get("feedback") or {}).get("can_continue"))
            for turn in conversation_turns
        ),
        "topic_report": topic_report,
        "error_patterns": [
            {"error_type": error_type, "count": count}
            for error_type, count in sorted(
                error_patterns.items(), key=lambda pair: -pair[1]
            )
        ][:5],
        "repair_candidates": repair_candidates,
        "errors": session_errors[:5],
        "next_review": "Anki/FSRS will schedule card recall; transfer follow-ups appear here when due.",
    }


def practice_overview(invoke_anki, workspace: Path) -> dict:
    """Build the Today dashboard without changing Anki scheduling."""
    state = load_state(workspace)
    items = discover_practice_items(invoke_anki)
    mastery = mastery_by_topic(invoke_anki, workspace)
    weakest = sorted(
        (
            {"topic_key": key, **value}
            for key, value in mastery.items()
        ),
        key=lambda item: (int(item.get("score") or 0), str(item.get("topic_key"))),
    )[:4]
    now = datetime.now(timezone.utc)
    due_tasks = []
    for task in (state.get("delayed_tasks") or {}).values():
        try:
            due = datetime.fromisoformat(str(task.get("due_at") or ""))
        except ValueError:
            continue
        if due <= now:
            due_tasks.append(task)
    errors = sorted(
        (state.get("error_notebook") or {}).values(),
        key=lambda entry: (-int(entry.get("count") or 0), str(entry.get("last_seen") or "")),
    )[:8]
    stage_names = ("recognition", "input", "controlled", "free", "speaking")
    stage_averages = {
        stage: round(sum(int(item.get("stages", {}).get(stage, 0)) for item in mastery.values()) / len(mastery))
        if mastery else 0
        for stage in stage_names
    }
    recommended = min(6, len(items))
    return {
        "available_cards": len(items),
        "recommended_cards": recommended,
        "estimated_minutes": max(1, round(recommended * 0.75 + 5)) if recommended else 0,
        "weakest_topics": weakest,
        "stage_averages": stage_averages,
        "errors": errors,
        "delayed_due": due_tasks,
        "scheduler_note": "Anki/FSRS remains the long-term scheduling authority.",
    }


def mastery_by_topic(invoke_anki, workspace: Path) -> dict:
    """Combine Anki retention evidence with local production evidence."""
    state = load_state(workspace)
    grouped: dict[str, list[dict]] = {}
    for item in discover_practice_items(invoke_anki):
        key = str(item.get("topic_key") or item.get("topic") or "unknown")
        grouped.setdefault(key, []).append(item)
    result = {}
    for key, items in grouped.items():
        anki_score = sum(float(item.get("strength") or 0) for item in items) / len(items)
        stats = (state.get("topic_stats") or {}).get(key, {})
        attempts = int(stats.get("controlled_attempts") or 0)
        first_try = int(stats.get("controlled_first_try_correct") or 0)
        input_attempts = int(stats.get("input_attempts") or 0)
        input_first_try = int(stats.get("input_first_try_correct") or 0)
        transfer_attempts = int(stats.get("transfer_attempts") or 0)
        transfer_correct = int(stats.get("transfer_correct") or 0)
        speaking_attempts = int(stats.get("speaking_attempts") or 0)
        speaking_correct = int(stats.get("speaking_correct") or 0)
        stages = {
            "recognition": round(anki_score),
            "input": round(input_first_try / input_attempts * 100) if input_attempts else 0,
            "controlled": round(first_try / attempts * 100) if attempts else 0,
            "free": round(transfer_correct / transfer_attempts * 100) if transfer_attempts else 0,
            "speaking": round(speaking_correct / speaking_attempts * 100) if speaking_attempts else 0,
        }
        # Interpretation evidence only counts for topics that own input cards,
        # so topics without them keep their original weighting.
        has_input_cards = any(item.get("mode") == "input" for item in items)
        if has_input_cards:
            score = min(100, round(
                stages["recognition"] * 0.60
                + stages["input"] * 0.08
                + stages["controlled"] * 0.13
                + stages["free"] * 0.11
                + stages["speaking"] * 0.08
            ))
        else:
            score = min(100, round(
                stages["recognition"] * 0.65
                + stages["controlled"] * 0.15
                + stages["free"] * 0.12
                + stages["speaking"] * 0.08
            ))
        if score >= 80 and stages["free"] >= 70 and stages["speaking"] >= 60 and (
            not has_input_cards or stages["input"] >= 60
        ):
            status = "mastered"
        elif score >= 55:
            status = "transfer-ready"
        elif score >= 30:
            status = "practising"
        else:
            status = "new"
        result[key] = {
            "topic": items[0].get("topic") or key,
            "score": score,
            "status": status,
            "cards": len(items),
            "controlled_attempts": attempts,
            "transfer_attempts": transfer_attempts,
            "speaking_attempts": speaking_attempts,
            "stages": stages,
        }
    return result
