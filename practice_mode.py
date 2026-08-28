"""Adaptive, task-based practice built from existing production cards."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path


PRACTICE_STATE_SCHEMA = "anki-generator-practice-state-v1"
PRACTICE_STATE_SUBDIR = Path(".anki-generator", "practice")
PRACTICE_STATE_FILENAME = "state-v1.json"

CORRECTION_MODEL_NAME = "AG Practice Correction v1"
CORRECTION_TEMPLATE_NAME = "AG Practice Correction"
CORRECTION_DECK_SUFFIX = "Practice Corrections"
CORRECTION_MARKER = "anki-generator-practice-correction-v1"
CORRECTION_FIELDS = (
    "Target",
    "Prompt",
    "Answer",
    "AG_SourceCardID",
    "AG_ErrorType",
)
CORRECTION_FRONT = (
    f"<!-- {CORRECTION_MARKER} -->"
    '<div class="ag-practice-label">USE IT IN ITALIAN</div>'
    '<div class="ag-practice-target">{{Target}}</div>'
    '<div class="ag-practice-prompt">{{Prompt}}</div>'
)
CORRECTION_BACK = (
    "{{FrontSide}}<hr id=\"answer\">"
    f"<!-- {CORRECTION_MARKER} -->"
    '<div class="ag-practice-label">MODEL ANSWER</div>'
    '<div class="ag-practice-answer">{{Answer}}</div>'
)
CORRECTION_CSS = f"""/* {CORRECTION_MARKER} */
.card {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 20px;
  line-height: 1.55;
  text-align: left;
  color: inherit;
  background: inherit;
  max-width: 680px;
  margin: 0 auto;
  padding: 28px 22px;
}}
.ag-practice-label {{
  opacity: .5;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .09em;
  margin-bottom: 10px;
}}
.ag-practice-target {{
  font-family: Georgia, "Times New Roman", serif;
  font-size: 38px;
  font-weight: 600;
  margin-bottom: 18px;
}}
.ag-practice-prompt, .ag-practice-answer {{
  padding: 14px 16px;
  border-radius: 8px;
  background: rgba(127,127,127,.10);
}}
.ag-practice-answer {{ border-left: 3px solid rgb(147,112,219); }}
"""


PRACTICE_TASKS = (
    {
        "title": "A message to a friend",
        "prompt_en": (
            "Write 2–4 natural Italian sentences telling a friend about "
            "something that happened today. Use every target expression."
        ),
        "prompt_fa": (
            "در ۲ تا ۴ جملهٔ طبیعی ایتالیایی، اتفاقی را که امروز افتاده برای "
            "یک دوست تعریف کن. از همهٔ عبارت‌های هدف استفاده کن."
        ),
    },
    {
        "title": "Ask for information",
        "prompt_en": (
            "Write a short Italian message asking an office or business for "
            "information. Use every target expression naturally."
        ),
        "prompt_fa": (
            "یک پیام کوتاه ایتالیایی برای درخواست اطلاعات از یک اداره یا کسب‌وکار "
            "بنویس. از همهٔ عبارت‌های هدف به‌طور طبیعی استفاده کن."
        ),
    },
    {
        "title": "Explain a problem",
        "prompt_en": (
            "Explain a small problem and what should happen next in 2–4 "
            "Italian sentences. Use every target expression."
        ),
        "prompt_fa": (
            "در ۲ تا ۴ جملهٔ ایتالیایی یک مشکل کوچک و کاری را که باید بعداً انجام "
            "شود توضیح بده. از همهٔ عبارت‌های هدف استفاده کن."
        ),
    },
    {
        "title": "A brief news report",
        "prompt_en": (
            "Write a very short Italian news-style report about an event. "
            "Use every target expression without forcing it."
        ),
        "prompt_fa": (
            "یک گزارش خبری بسیار کوتاه به ایتالیایی دربارهٔ یک رویداد بنویس. از "
            "همهٔ عبارت‌های هدف بدون استفادهٔ مصنوعی بهره ببر."
        ),
    },
    {
        "title": "Make a plan",
        "prompt_en": (
            "Write 2–4 Italian sentences proposing a plan for the coming "
            "week. Use every target expression naturally."
        ),
        "prompt_fa": (
            "در ۲ تا ۴ جملهٔ ایتالیایی برای هفتهٔ آینده برنامه‌ای پیشنهاد کن. از "
            "همهٔ عبارت‌های هدف به‌طور طبیعی استفاده کن."
        ),
    },
    {
        "title": "A polite reply",
        "prompt_en": (
            "Write a polite Italian reply to someone who has contacted you. "
            "Use every target expression in 2–4 sentences."
        ),
        "prompt_fa": (
            "یک پاسخ مؤدبانهٔ ایتالیایی به کسی که با تو تماس گرفته بنویس. در ۲ تا "
            "۴ جمله از همهٔ عبارت‌های هدف استفاده کن."
        ),
    },
)


def _field_value(note: dict, field_name: str) -> str:
    return str(
        ((note.get("fields") or {}).get(field_name) or {}).get("value")
        or ""
    )


def _chunks(values, size=500):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _plain_card_text(value: str, limit: int = 1200) -> str:
    """Remove executable/card-layout content before sending context to AI."""
    cleaned = re.sub(
        r"<(style|script|audio)\b[^>]*>.*?</\1>",
        " ",
        str(value or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def discover_practice_candidates(
    invoke_anki,
    *,
    source_model_name: str,
    recall_model_name: str,
) -> list[dict]:
    """Read studied production cards and return one safe candidate per word."""
    card_ids = invoke_anki(
        "findCards",
        {"query": f'card:"AG Production Recall" -is:new'},
    ) or []
    cards = []
    for chunk in _chunks(card_ids):
        cards.extend(invoke_anki("cardsInfo", {"cards": chunk}) or [])

    allowed_models = {source_model_name, recall_model_name}
    cards = [
        card for card in cards
        if str(card.get("modelName") or "") in allowed_models
        and int(card.get("reps") or 0) > 0
    ]
    note_ids = sorted({int(card.get("note") or 0) for card in cards})
    notes = []
    for chunk in _chunks(note_ids):
        notes.extend(invoke_anki("notesInfo", {"notes": chunk}) or [])
    notes_by_id = {
        int(note.get("noteId") or 0): note
        for note in notes
        if note
    }

    candidates_by_word = {}
    for card in cards:
        note_id = int(card.get("note") or 0)
        note = notes_by_id.get(note_id)
        if not note:
            continue
        model_name = str(note.get("modelName") or "")
        word = _field_value(note, "Word").strip()
        if not word:
            continue
        if model_name == recall_model_name:
            front = _field_value(note, "ProductionFront")
            back = _field_value(note, "ProductionBack")
        else:
            front = _field_value(note, "AG_ProductionFront_v1")
            back = _field_value(note, "AG_ProductionBack_v1")
        if not front.strip() or not back.strip():
            continue

        reps = int(card.get("reps") or 0)
        lapses = int(card.get("lapses") or 0)
        interval = max(0, int(card.get("interval") or 0))
        factor = int(card.get("factor") or 2500)
        weakness = (
            lapses * 18
            + max(0, 21 - min(interval, 21))
            + max(0, 2500 - factor) / 100
            + min(reps, 20) / 20
        )
        candidate = {
            "word": word,
            "identity": word.casefold(),
            "note_id": note_id,
            "card_id": int(card.get("cardId") or 0),
            "model_name": model_name,
            "interval": interval,
            "reps": reps,
            "lapses": lapses,
            "factor": factor,
            "weakness": float(weakness),
            "reference": _plain_card_text(back),
            "cue": _plain_card_text(front, limit=500),
        }
        previous = candidates_by_word.get(candidate["identity"])
        if previous is None or candidate["weakness"] > previous["weakness"]:
            candidates_by_word[candidate["identity"]] = candidate
    return list(candidates_by_word.values())


def default_practice_state() -> dict:
    return {
        "schema": PRACTICE_STATE_SCHEMA,
        "sessions_completed": 0,
        "recent_words": [],
        "mistakes": {},
        "last_session": None,
    }


def practice_state_path(workspace: Path) -> Path:
    return workspace.resolve() / PRACTICE_STATE_SUBDIR / PRACTICE_STATE_FILENAME


def load_practice_state(workspace: Path) -> dict:
    path = practice_state_path(workspace)
    if not path.exists():
        return default_practice_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Practice history is unreadable: {path}. Nothing was changed."
        ) from error
    if not isinstance(state, dict) or state.get("schema") != PRACTICE_STATE_SCHEMA:
        raise ValueError(
            f"Practice history has an unsupported format: {path}."
        )
    state.setdefault("sessions_completed", 0)
    state.setdefault("recent_words", [])
    state.setdefault("mistakes", {})
    state.setdefault("last_session", None)
    return state


def save_practice_state(workspace: Path, state: dict) -> Path:
    path = practice_state_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".practice-state.", suffix=".tmp", dir=str(path.parent)
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


def select_practice_targets(
    candidates: list[dict],
    state: dict,
    *,
    count: int = 3,
    today: date | None = None,
) -> list[dict]:
    """Choose effortful targets while rotating recently practiced words."""
    if count < 1:
        raise ValueError("Practice count must be at least one.")
    recent = {
        str(word).casefold()
        for word in (state.get("recent_words") or [])[-12:]
    }
    available = [item for item in candidates if item["identity"] not in recent]
    if len(available) < count:
        available = list(candidates)
    day = (today or date.today()).isoformat()

    def rank(item):
        jitter_bytes = hashlib.sha256(
            f"{day}|{item['identity']}".encode("utf-8")
        ).digest()[:4]
        jitter = int.from_bytes(jitter_bytes, "big") / (2**32)
        return item["weakness"] + jitter * 6

    ranked = sorted(available, key=rank, reverse=True)
    if len(ranked) <= count:
        return ranked

    # Keep one mature item for transfer, rather than practicing only lapses.
    mature = [item for item in ranked if item["interval"] >= 21]
    chosen = ranked[:count]
    if mature and not any(item["interval"] >= 21 for item in chosen):
        chosen[-1] = mature[0]
    deduplicated = []
    seen = set()
    for item in chosen:
        if item["identity"] not in seen:
            seen.add(item["identity"])
            deduplicated.append(item)
    return deduplicated


def build_practice_task(targets: list[dict], state: dict) -> dict:
    session_number = int(state.get("sessions_completed") or 0)
    identities = "|".join(sorted(item["identity"] for item in targets))
    digest = hashlib.sha256(
        f"{date.today().isoformat()}|{session_number}|{identities}".encode("utf-8")
    ).digest()
    template = PRACTICE_TASKS[int.from_bytes(digest[:2], "big") % len(PRACTICE_TASKS)]
    return {
        **template,
        "prompt_en": (
            template["prompt_en"]
            + " If this situation does not fit the target expressions, choose "
            "another realistic situation of your own."
        ),
        "prompt_fa": (
            template["prompt_fa"]
            + " اگر این موقعیت با عبارت‌های هدف سازگار نیست، یک موقعیت واقعی "
            "دیگر را خودت انتخاب کن."
        ),
        "target_words": [item["word"] for item in targets],
    }


def update_practice_state(
    state: dict,
    targets: list[dict],
    feedback: dict,
) -> list[dict]:
    """Record results and return errors that have now occurred twice."""
    now = datetime.now(timezone.utc).isoformat()
    mistakes = state.setdefault("mistakes", {})
    results = feedback.get("target_results") or []
    results_by_word = {
        str(result.get("word") or "").casefold(): result
        for result in results
        if isinstance(result, dict)
    }
    repeated = []
    for target in targets:
        word = target["word"]
        identity = target["identity"]
        result = results_by_word.get(identity) or {}
        correct = bool(result.get("correct"))
        if correct:
            for key, entry in mistakes.items():
                if key.startswith(identity + "|") and isinstance(entry, dict):
                    entry["count"] = 0
            continue
        error_type = str(result.get("error_type") or "other").strip().lower()
        key = f"{identity}|{error_type}"
        entry = mistakes.setdefault(key, {
            "word": word,
            "error_type": error_type,
            "count": 0,
            "last_offered_count": 0,
        })
        entry["count"] = int(entry.get("count") or 0) + 1
        entry["last_seen"] = now
        entry["feedback_en"] = str(result.get("feedback_en") or "").strip()
        entry["feedback_fa"] = str(result.get("feedback_fa") or "").strip()
        entry["correction_prompt_en"] = str(
            result.get("correction_prompt_en") or ""
        ).strip()
        entry["correction_prompt_fa"] = str(
            result.get("correction_prompt_fa") or ""
        ).strip()
        entry["correction_answer_it"] = str(
            result.get("correction_answer_it") or ""
        ).strip()
        if (
            entry["count"] >= 2
            and entry["count"] - int(entry.get("last_offered_count") or 0) >= 2
        ):
            entry["state_key"] = key
            entry["source_card_id"] = target["card_id"]
            repeated.append(entry)

    recent_words = list(state.get("recent_words") or [])
    recent_words.extend(target["word"] for target in targets)
    state["recent_words"] = recent_words[-30:]
    state["sessions_completed"] = int(state.get("sessions_completed") or 0) + 1
    state["last_session"] = {
        "at": now,
        "targets": [target["word"] for target in targets],
        "model": str(feedback.get("_gemini_model") or "unknown"),
    }
    return repeated


def mark_correction_offer(state: dict, entries: list[dict]) -> None:
    mistakes = state.get("mistakes") or {}
    for offered in entries:
        key = offered.get("state_key")
        entry = mistakes.get(key)
        if isinstance(entry, dict):
            entry["last_offered_count"] = int(entry.get("count") or 0)


def inspect_correction_model(invoke_anki) -> dict:
    names = invoke_anki("modelNamesAndIds") or {}
    if CORRECTION_MODEL_NAME not in names:
        return {"exists": False}
    fields = invoke_anki(
        "modelFieldNames", {"modelName": CORRECTION_MODEL_NAME}
    ) or []
    templates = invoke_anki(
        "modelTemplates", {"modelName": CORRECTION_MODEL_NAME}
    ) or {}
    styling = invoke_anki(
        "modelStyling", {"modelName": CORRECTION_MODEL_NAME}
    ) or {}
    expected_templates = {
        CORRECTION_TEMPLATE_NAME: {
            "Front": CORRECTION_FRONT,
            "Back": CORRECTION_BACK,
        }
    }
    if (
        fields != list(CORRECTION_FIELDS)
        or templates != expected_templates
        or str(styling.get("css") or "").replace("\r\n", "\n").strip()
        != CORRECTION_CSS.strip()
    ):
        raise ValueError(
            f'A note type named "{CORRECTION_MODEL_NAME}" exists but is not '
            "the exact app-owned version. Nothing was changed."
        )
    return {"exists": True, "model_id": int(names[CORRECTION_MODEL_NAME])}


def ensure_correction_model(invoke_anki) -> dict:
    current = inspect_correction_model(invoke_anki)
    if current["exists"]:
        return current
    invoke_anki(
        "createModel",
        {
            "modelName": CORRECTION_MODEL_NAME,
            "inOrderFields": list(CORRECTION_FIELDS),
            "css": CORRECTION_CSS,
            "isCloze": False,
            "cardTemplates": [{
                "Name": CORRECTION_TEMPLATE_NAME,
                "Front": CORRECTION_FRONT,
                "Back": CORRECTION_BACK,
            }],
        },
    )
    verified = inspect_correction_model(invoke_anki)
    if not verified["exists"]:
        raise RuntimeError("Anki did not finish creating the correction note type.")
    return verified


def create_correction_cards(
    invoke_anki,
    entries: list[dict],
    *,
    source_deck: str,
) -> dict:
    """Create only explicitly approved, deduplicated correction notes."""
    if not entries:
        return {"added": 0, "skipped": 0}
    ensure_correction_model(invoke_anki)
    deck_name = f"{source_deck}::{CORRECTION_DECK_SUFFIX}"
    invoke_anki("createDeck", {"deck": deck_name})
    added = 0
    skipped = 0
    for entry in entries:
        word = str(entry.get("word") or "").strip()
        error_type = str(entry.get("error_type") or "other").strip()
        answer = str(entry.get("correction_answer_it") or "").strip()
        prompt_en = str(entry.get("correction_prompt_en") or "").strip()
        prompt_fa = str(entry.get("correction_prompt_fa") or "").strip()
        if not word or not answer or not (prompt_en or prompt_fa):
            skipped += 1
            continue
        escaped_word = word.replace("\\", "\\\\").replace('"', '\\"')
        escaped_error = error_type.replace("\\", "\\\\").replace('"', '\\"')
        existing = invoke_anki(
            "findNotes",
            {
                "query": (
                    f'note:"{CORRECTION_MODEL_NAME}" '
                    f'Target:"{escaped_word}" AG_ErrorType:"{escaped_error}"'
                )
            },
        ) or []
        if existing:
            skipped += 1
            continue
        prompt_parts = []
        if prompt_en:
            prompt_parts.append(f'<div>{html.escape(prompt_en)}</div>')
        if prompt_fa:
            prompt_parts.append(
                '<div lang="fa" dir="rtl" style="margin-top:8px;">'
                f'{html.escape(prompt_fa)}</div>'
            )
        feedback_en = str(entry.get("feedback_en") or "").strip()
        feedback_fa = str(entry.get("feedback_fa") or "").strip()
        answer_parts = [
            '<div style="font-size:24px;font-weight:650;">'
            f'{html.escape(answer)}</div>'
        ]
        if feedback_en:
            answer_parts.append(
                f'<div style="margin-top:10px;">{html.escape(feedback_en)}</div>'
            )
        if feedback_fa:
            answer_parts.append(
                '<div lang="fa" dir="rtl" style="margin-top:8px;">'
                f'{html.escape(feedback_fa)}</div>'
            )
        safe_error_tag = re.sub(r"[^a-z0-9_-]+", "_", error_type.casefold())
        note_id = invoke_anki(
            "addNote",
            {
                "note": {
                    "deckName": deck_name,
                    "modelName": CORRECTION_MODEL_NAME,
                    "fields": {
                        "Target": word,
                        "Prompt": "".join(prompt_parts),
                        "Answer": "".join(answer_parts),
                        "AG_SourceCardID": str(entry.get("source_card_id") or ""),
                        "AG_ErrorType": error_type,
                    },
                    "tags": [
                        "ag-practice-correction",
                        f"ag_error_{safe_error_tag}",
                    ],
                    # The explicit model+target+error query above is the real
                    # dedupe boundary. Different errors for one word may each
                    # deserve a separate correction card.
                    "options": {"allowDuplicate": True},
                }
            },
        )
        if note_id:
            added += 1
        else:
            skipped += 1
    return {"added": added, "skipped": skipped}
