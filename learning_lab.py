"""Isolated voice-first speaking practice for the Learning Lab.

This module is intentionally separate from the existing practice workflow.
It reads Anki data but only writes its own local history. Raw audio is never
stored; only the speech transcript and compact practice metadata are saved.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from practice_mode import discover_practice_candidates, select_practice_targets

SCHEMA = "anki-generator-learning-lab-v1"
STATE_PATH = Path(".anki-generator", "learning-lab", "state-v1.json")
SPEAKING_SPRINT_CONFIG = {
    "rounds": 3,
    # Browser speech recognition may end an utterance as soon as it detects a
    # pause.  Do not reject a real sentence using an arbitrary client timer;
    # the feedback model checks whether the translation itself is complete.
    "minimum_seconds": 0,
    # A full-sentence translation is never one word; a single "word" is
    # usually a recognition hallucination from breath or background noise.
    "minimum_words": 2,
    "max_feedback_attempts": 2,
    "preparation_seconds": 5,
}

def default_state() -> dict:
    return {
        "schema": SCHEMA,
        "sessions_completed": 0,
        "speaking_seconds": 0,
        "recent_words": [],
        "trouble_words": {},
        "grammar_patterns": {},
        "spoken_review": {},
        "error_memory": {},
        "word_lookups": {},
        "fluency_summary": {
            "attempts": 0,
            "average_wpm": 0,
            "average_voice_ratio": 0,
            "average_start_delay": 0,
        },
        "sessions": [],
    }

def load_state(workspace: Path) -> dict:
    path = workspace.resolve() / STATE_PATH
    if not path.exists():
        return default_state()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Learning Lab history is unreadable; nothing was changed.") from error
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("Learning Lab history has an unsupported format.")
    value.setdefault("trouble_words", {})
    value.setdefault("grammar_patterns", {})
    value.setdefault("spoken_review", {})
    value.setdefault("error_memory", {})
    value.setdefault("word_lookups", {})
    value.setdefault("fluency_summary", default_state()["fluency_summary"])
    return value

def save_state(workspace: Path, state: dict) -> Path:
    path = workspace.resolve() / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".learning-lab-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        try: os.unlink(temp)
        except OSError: pass
        raise
    return path

def select_targets(
    invoke_anki,
    state: dict,
    source_model: str,
    recall_model: str,
    count: int = 1,
    exclude_words: list[str] | None = None,
) -> list[dict]:
    candidates = discover_practice_candidates(invoke_anki, source_model_name=source_model, recall_model_name=recall_model)
    candidates = [
        item for item in candidates
        if str(item.get("example_it") or "").strip()
        and str(item.get("example_en") or "").strip()
    ]
    excluded = {str(word).casefold().strip() for word in (exclude_words or [])}
    candidates = [item for item in candidates if item["identity"] not in excluded]
    now = datetime.now(timezone.utc)
    review = state.get("spoken_review") or {}
    due = []
    for item in candidates:
        scheduled = review.get(item["identity"]) or {}
        try:
            due_at = datetime.fromisoformat(str(scheduled.get("due_at") or ""))
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if due_at <= now:
            due.append(item)
    if due:
        due.sort(key=lambda item: str((review.get(item["identity"]) or {}).get("due_at") or ""))
        return due[:count]

    trouble = state.get("trouble_words") or {}
    troubled = [
        item for item in candidates
        if int((trouble.get(item["identity"]) or {}).get("misses") or 0) > 0
    ]
    if troubled:
        troubled.sort(
            key=lambda item: (
                int((trouble.get(item["identity"]) or {}).get("misses") or 0),
                item["weakness"],
            ),
            reverse=True,
        )
        return troubled[:count]
    return select_practice_targets(candidates, state, count=count)


def _italian_scaffold(sentence: str, target_word: str) -> str:
    """Reveal a short beginning without giving away the target itself."""
    tokens = str(sentence or "").strip().split()
    target = str(target_word or "").casefold().strip(".,;:!?")
    visible = []
    for token in tokens:
        if token.casefold().strip(".,;:!?") == target:
            break
        visible.append(token)
        if len(visible) >= 3:
            break
    if not visible and tokens:
        visible = tokens[:1]
    return (" ".join(visible).rstrip(".,;:!?") + " …") if visible else ""


def _daily_progress(state: dict) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    correct = sum(
        1 for item in (state.get("sessions") or [])
        if str(item.get("at") or "").startswith(today)
        and bool(item.get("evaluation_reliable", True))
        and not bool((item.get("feedback") or {}).get("retry_needed"))
    )
    return {"correct_sentences": correct, "goal": 5}


def _translation_task(target: dict, ladder_level: int) -> dict:
    """Build one meaning-first English-to-Italian speaking prompt."""
    try:
        level = max(1, min(3, int(ladder_level or 1)))
    except (TypeError, ValueError):
        level = 1
    labels = {
        1: "Guided translation",
        2: "New translation",
        3: "Final translation",
    }
    return {
        "title": labels[level],
        "task_type": "translation",
        "ladder_level": level,
        "prompt_en": str(target.get("example_en") or "").strip(),
        "prompt_fa": "جملهٔ انگلیسی را به ایتالیایی بگو.",
        "source_en": str(target.get("example_en") or "").strip(),
        "response_mode": "voice",
        "target_words": [str(target.get("word") or "").strip()],
        "hint_it": _italian_scaffold(
            str(target.get("example_it") or ""),
            str(target.get("word") or ""),
        ),
        "hint_visible": level == 1,
        "hint_cost": level - 1,
    }


def build_session(
    invoke_anki,
    state: dict,
    source_model: str,
    recall_model: str,
    count: int = 1,
    ladder_level: int = 1,
    exclude_words: list[str] | None = None,
) -> dict:
    targets = select_targets(
        invoke_anki,
        state,
        source_model,
        recall_model,
        count,
        exclude_words=exclude_words,
    )
    if not targets:
        return {
            "targets": [],
            "task": None,
            "sprint": dict(SPEAKING_SPRINT_CONFIG),
            "daily": _daily_progress(state),
        }
    task = _translation_task(targets[0], ladder_level)
    task["seen_grammar_patterns"] = {
        str(key): int((value or {}).get("exposures") or 0)
        for key, value in (state.get("grammar_patterns") or {}).items()
    }
    identity = str(targets[0].get("identity") or targets[0].get("word") or "").casefold().strip()
    scheduled = (state.get("spoken_review") or {}).get(identity) or {}
    task["review_status"] = {
        "scheduled": bool(scheduled),
        "due_at": str(scheduled.get("due_at") or ""),
        "successes": int(scheduled.get("successes") or 0),
        "lapses": int(scheduled.get("lapses") or 0),
    }
    frequent_errors = sorted(
        (state.get("error_memory") or {}).values(),
        key=lambda value: (int((value or {}).get("count") or 0), str((value or {}).get("updated_at") or "")),
        reverse=True,
    )[:2]
    return {
        "targets": targets,
        "task": task,
        "sprint": dict(SPEAKING_SPRINT_CONFIG),
        "daily": _daily_progress(state),
        "coach": {
            "due_review": bool(scheduled),
            "frequent_errors": frequent_errors,
            "fluency": state.get("fluency_summary") or {},
        },
    }


def _bounded_float(value, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, round(float(value), 2)))
    except (TypeError, ValueError):
        return minimum


def _update_spoken_review(state: dict, identity: str, correct: bool, now: datetime) -> None:
    review = state.setdefault("spoken_review", {})
    previous = review.get(identity) or {}
    if correct:
        successes = min(20, int(previous.get("successes") or 0) + 1)
        intervals = (1, 3, 7, 14, 30, 60)
        interval_days = intervals[min(successes - 1, len(intervals) - 1)]
        review[identity] = {
            "successes": successes,
            "lapses": int(previous.get("lapses") or 0),
            "interval_days": interval_days,
            "due_at": (now + timedelta(days=interval_days)).isoformat(),
            "updated_at": now.isoformat(),
        }
    else:
        review[identity] = {
            "successes": 0,
            "lapses": min(20, int(previous.get("lapses") or 0) + 1),
            "interval_days": 0,
            "due_at": (now + timedelta(minutes=10)).isoformat(),
            "updated_at": now.isoformat(),
        }


def _update_error_memory(state: dict, feedback: dict, now: str) -> None:
    focus = (feedback or {}).get("focus") or {}
    category = str(focus.get("category") or "").casefold().strip()
    if not category or category == "none":
        return
    memory = state.setdefault("error_memory", {})
    previous = memory.get(category) or {}
    memory[category] = {
        "category": category,
        "count": min(100, int(previous.get("count") or 0) + 1),
        "learner_fragment": str(focus.get("learner_fragment") or "")[:200],
        "corrected_fragment": str(focus.get("corrected_fragment") or "")[:200],
        "explanation_en": str(focus.get("explanation_en") or "")[:400],
        "updated_at": now,
    }


def _update_fluency_summary(state: dict, fluency: dict) -> None:
    if not fluency:
        return
    summary = state.setdefault("fluency_summary", default_state()["fluency_summary"])
    previous_attempts = int(summary.get("attempts") or 0)
    attempts = previous_attempts + 1
    for output_key, input_key in (
        ("average_wpm", "words_per_minute"),
        ("average_voice_ratio", "voice_ratio"),
        ("average_start_delay", "start_delay_seconds"),
    ):
        previous = float(summary.get(output_key) or 0)
        current = float(fluency.get(input_key) or 0)
        summary[output_key] = round(((previous * previous_attempts) + current) / attempts, 1)
    summary["attempts"] = attempts

def record_session(
    state: dict,
    targets: list[dict],
    *,
    response: str,
    feedback: dict,
    mode: str = "text",
    duration_seconds: float = 0,
    attempt: int = 1,
    round_number: int = 1,
    phase: str = "translation",
    fluency: dict | None = None,
    evaluation_reliable: bool = True,
) -> dict:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    safe_mode = "voice" if mode == "voice" else "text"
    try:
        safe_duration = max(0, min(300, round(float(duration_seconds), 1)))
    except (TypeError, ValueError):
        safe_duration = 0
    try:
        safe_attempt = max(1, min(10, int(attempt)))
    except (TypeError, ValueError):
        safe_attempt = 1
    try:
        safe_round = max(1, min(20, int(round_number)))
    except (TypeError, ValueError):
        safe_round = 1
    result = {
        "at": now,
        "targets": [str(item.get("word")) for item in targets],
        "response": str(response),
        "feedback": feedback,
        "mode": safe_mode,
        "duration_seconds": safe_duration,
        "attempt": safe_attempt,
        "round": safe_round,
        "phase": "transfer" if phase == "transfer" else "translation",
        "evaluation_reliable": bool(evaluation_reliable),
    }
    word_count = len(str(response or "").split())
    safe_fluency = {
        "words_per_minute": _bounded_float(
            (word_count / safe_duration * 60) if safe_duration else 0, 0, 400,
        ),
        "voice_ratio": _bounded_float((fluency or {}).get("voice_ratio"), 0, 1),
        "start_delay_seconds": _bounded_float((fluency or {}).get("start_delay_seconds"), 0, 60),
        "longest_pause_seconds": _bounded_float((fluency or {}).get("longest_pause_seconds"), 0, 60),
    }
    if safe_mode == "voice":
        result["fluency"] = safe_fluency
    state.setdefault("sessions", []).append(result)
    state["sessions"] = state["sessions"][-100:]
    state["sessions_completed"] = int(state.get("sessions_completed") or 0) + 1
    if safe_mode == "voice":
        state["speaking_seconds"] = round(
            float(state.get("speaking_seconds") or 0) + safe_duration,
            1,
        )
    recent = list(state.get("recent_words") or [])
    recent.extend(result["targets"])
    state["recent_words"] = recent[-30:]
    trouble = state.setdefault("trouble_words", {})
    results = (feedback or {}).get("target_results") or []
    if not evaluation_reliable:
        return result
    for target_result in results:
        identity = str(target_result.get("word") or "").casefold().strip()
        if not identity:
            continue
        if bool(target_result.get("correct")):
            remaining = max(0, int((trouble.get(identity) or {}).get("misses") or 0) - 1)
            if remaining:
                trouble[identity] = {"misses": remaining, "updated_at": now}
            else:
                trouble.pop(identity, None)
            _update_spoken_review(state, identity, True, now_dt)
        else:
            misses = min(20, int((trouble.get(identity) or {}).get("misses") or 0) + 1)
            trouble[identity] = {"misses": misses, "updated_at": now}
            _update_spoken_review(state, identity, False, now_dt)
    pattern = (feedback or {}).get("new_pattern") or {}
    pattern_key = str(pattern.get("key") or "").casefold().strip()
    if bool(pattern.get("detected")) and pattern_key:
        patterns = state.setdefault("grammar_patterns", {})
        previous = patterns.get(pattern_key) or {}
        patterns[pattern_key] = {
            "label_it": str(pattern.get("label_it") or pattern_key),
            "exposures": min(20, int(previous.get("exposures") or 0) + 1),
            "updated_at": now,
        }
    _update_error_memory(state, feedback, now)
    if safe_mode == "voice":
        _update_fluency_summary(state, safe_fluency)
    return result

WORD_LOOKUP_EVENTS = ("peek", "guess", "reveal", "add_requested")

MAX_WORD_LOOKUPS = 60


def record_word_help(
    state: dict,
    word: str,
    event: str,
    *,
    guessed_correctly: bool | None = None,
) -> dict:
    """Remember one word-help interaction so repeated lookups resurface.

    Word lookups are retention gaps observed mid-speech: a word the learner
    had to stop and ask about is a prime spaced-review candidate.
    """
    display = str(word or "").strip()[:60]
    if not display:
        raise ValueError("No word was provided for the lookup.")
    normalized_event = str(event or "peek").strip()
    if normalized_event not in WORD_LOOKUP_EVENTS:
        raise ValueError("Unsupported word-help event.")
    identity = display.casefold()
    now = datetime.now(timezone.utc).isoformat()
    lookups = state.setdefault("word_lookups", {})
    entry = lookups.setdefault(identity, {
        "word": display,
        "peeks": 0,
        "guesses": 0,
        "correct_guesses": 0,
        "reveals": 0,
        "add_requests": 0,
        "first_seen": now,
    })
    entry["word"] = display
    entry["last_seen"] = now
    if normalized_event == "peek":
        entry["peeks"] = min(99, int(entry.get("peeks") or 0) + 1)
    elif normalized_event == "guess":
        entry["guesses"] = min(99, int(entry.get("guesses") or 0) + 1)
        if guessed_correctly:
            entry["correct_guesses"] = min(
                99, int(entry.get("correct_guesses") or 0) + 1
            )
    elif normalized_event == "reveal":
        entry["reveals"] = min(99, int(entry.get("reveals") or 0) + 1)
    elif normalized_event == "add_requested":
        entry["add_requests"] = min(99, int(entry.get("add_requests") or 0) + 1)
    # Bound local state without relying on lexical order of timestamps alone.
    if len(lookups) > MAX_WORD_LOOKUPS:
        oldest = sorted(
            lookups.items(),
            key=lambda pair: str(pair[1].get("first_seen") or ""),
        )
        for key, _ in oldest[:len(lookups) - MAX_WORD_LOOKUPS]:
            lookups.pop(key, None)
    return entry


def transcript_plausibility_problem(
    transcript: str,
    fluency: dict | None,
    duration_seconds: float | None,
) -> str:
    """Return a reason when the transcript outgrew the measured speech.

    Gemini sees the reference sentence, so a near-silent clip can come back
    "transcribed" as the full model answer. The browser's microphone-energy
    measurement puts a hard physical ceiling on how many words can have been
    spoken (~3 words per second of voiced audio, plus a small allowance).
    """
    words = len([word for word in str(transcript or "").split() if word.strip()])
    if words == 0:
        return ""
    try:
        duration = max(0.0, float(duration_seconds or 0))
    except (TypeError, ValueError):
        duration = 0.0
    # Without any measured duration there is nothing to falsify against;
    # the real client always reports one.
    if duration <= 0:
        return ""
    try:
        ratio = max(0.0, min(1.0, float((fluency or {}).get("voice_ratio") or 0)))
    except (TypeError, ValueError):
        ratio = 0.0
    voiced_seconds = ratio * duration if ratio else duration
    allowance = int(voiced_seconds * 3) + 2
    if words <= allowance:
        return ""
    return (
        f"The transcript has {words} words but only about {voiced_seconds:.1f} "
        "seconds of measured voice, so it cannot be trusted as what you said. "
        "This attempt was not graded or counted."
    )
