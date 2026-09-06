"""Cross-surface recurring-error insights and curriculum recommendations.

Merges the three local practice stores (grammar practice, speaking lab,
word practice) into one normalized error view, then deterministically maps
the strongest recurring error patterns back onto the built-in grammar
curriculum so the learner always has a concrete "study this next" answer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from grammar_practice import load_state as load_grammar_state


SOURCE_LABELS = {
    "grammar_practice": "Grammar practice",
    "speaking_lab": "Speaking Lab",
    "word_practice": "Word practice",
}

# Error taxonomy -> curriculum keyword families. Used with title/hint token
# overlap so a category always lands on the topics that actually train it.
ERROR_TOPIC_ALIASES = {
    "article": ("articoli", "articolo", "articolat"),
    "agreement": ("accordo", "aggettiv", "genere", "numero", "plural"),
    "pronoun": ("pronom", "ne_ci", "partitiv"),
    "preposition": ("preposizion",),
    "tense_mood": (
        "passato", "imperfetto", "futuro", "condizional", "congiuntiv",
        "trapassato", "presente", "imperativ", "gerundio", "essere_avere",
    ),
    "word_form": ("genere", "plural", "conjugation", "presente"),
    "wrong_meaning": ("sapere", "conoscere", "stare", "essere", "bello", "buono"),
    "word_order": ("clitic", "pronoun", "pronom"),
    "sentence_correction": ("errore", "mistake"),
}


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _now_key(entry: dict, *fields: str) -> str:
    for field in fields:
        value = str(entry.get(field) or "").strip()
        if value:
            return value
    return ""


def collect_errors(workspace: Path) -> dict:
    """Merge error evidence from all three local practice stores."""
    workspace = Path(workspace)
    patterns: dict[tuple[str, str, str], dict] = {}

    def _add(source: str, error_type: str, label: str, count: int,
             last_seen: str, sample: str = "", stage: str = "") -> None:
        count = max(0, int(count or 0))
        if count <= 0:
            return
        key = (source, str(error_type or "other"), str(label or "general"))
        entry = patterns.setdefault(key, {
            "source": source,
            "source_label": SOURCE_LABELS.get(source, source),
            "error_type": str(error_type or "other"),
            "label": str(label or "general"),
            "stage": stage,
            "count": 0,
            "last_seen": "",
            "sample": "",
        })
        entry["count"] += count
        if last_seen > entry["last_seen"]:
            entry["last_seen"] = last_seen
            if sample:
                entry["sample"] = str(sample)[:200]

    # 1. Grammar practice error notebook (strongest, structured evidence).
    try:
        grammar_state = load_grammar_state(workspace)
    except ValueError:
        grammar_state = {}
    for entry in (grammar_state.get("error_notebook") or {}).values():
        _add(
            "grammar_practice",
            str(entry.get("error_type") or "other"),
            str(entry.get("topic") or entry.get("topic_key") or "general"),
            int(entry.get("count") or 0),
            _now_key(entry, "last_seen", "first_seen"),
            str(entry.get("last_response") or ""),
            stage=str(entry.get("stage") or ""),
        )

    # 2. Speaking Lab error memory keyed by feedback category.
    lab_state = _read_json(
        workspace / ".anki-generator" / "learning-lab" / "state-v1.json"
    ) or {}
    for entry in (lab_state.get("error_memory") or {}).values():
        _add(
            "speaking_lab",
            str(entry.get("category") or "other"),
            str(entry.get("category") or "general").replace("_", " "),
            int(entry.get("count") or 0),
            _now_key(entry, "updated_at"),
            str(entry.get("learner_fragment") or ""),
        )

    # 2b. Mid-speech word lookups: words the learner had to stop and ask
    # about are retention gaps, so repeated ones belong on the dashboard.
    for entry in (lab_state.get("word_lookups") or {}).values():
        if not isinstance(entry, dict):
            continue
        peeks = int(entry.get("peeks") or 0)
        reveals = int(entry.get("reveals") or 0)
        correct_guesses = int(entry.get("correct_guesses") or 0)
        if peeks + reveals < 2 or correct_guesses >= 2:
            # A single lookup is curiosity; two or more is a gap, unless the
            # learner keeps answering it correctly.
            continue
        _add(
            "speaking_lab",
            "word_lookup",
            str(entry.get("word") or "general"),
            peeks + reveals,
            _now_key(entry, "last_seen", "first_seen"),
            f"{peeks} lookups, {reveals} reveals",
        )

    # 3. Word-practice mistakes (word-level production errors).
    word_state = _read_json(
        workspace / ".anki-generator" / "practice" / "state-v1.json"
    ) or {}
    for entry in (word_state.get("mistakes") or {}).values():
        if not isinstance(entry, dict):
            continue
        _add(
            "word_practice",
            str(entry.get("error_type") or "other"),
            str(entry.get("word") or "general"),
            int(entry.get("count") or 0),
            _now_key(entry, "last_seen"),
            str(entry.get("feedback_en") or ""),
        )

    ranked = sorted(
        patterns.values(),
        key=lambda entry: (
            -entry["count"],
            entry["last_seen"],
            entry["label"],
        ),
    )
    return {
        "patterns": ranked,
        "top": ranked[:8],
        "total_errors": sum(entry["count"] for entry in ranked),
    }


def _topic_tokens(topic: dict) -> set[str]:
    text = " ".join((
        str(topic.get("title_it") or ""),
        str(topic.get("title_en") or ""),
        str(topic.get("prompt_hint") or ""),
    )).casefold()
    return set(re.findall(r"[a-zà-ú']{3,}", text))


def recommend_topics(
    patterns: list[dict],
    catalogs: dict[str, dict],
    mastery: dict | None = None,
    limit: int = 3,
) -> list[dict]:
    """Map recurring error patterns onto curriculum topics deterministically."""
    mastery = mastery or {}
    scored: dict[str, dict] = {}
    for pattern in patterns:
        error_type = str(pattern.get("error_type") or "other")
        haystack = " ".join((
            error_type,
            str(pattern.get("label") or ""),
            str(pattern.get("sample") or ""),
        )).casefold()
        weight = min(5, max(1, int(pattern.get("count") or 1)))
        for _catalog_name, catalog in catalogs.items():
            for key, topic in catalog.items():
                if str(mastery.get(key, {}).get("status") or "") == "mastered":
                    continue
                topic_text = " ".join((
                    str(topic.get("title_it") or ""),
                    str(topic.get("title_en") or ""),
                    str(topic.get("prompt_hint") or ""),
                )).casefold()
                # The error family must have topical affinity with the
                # topic itself: an alias of the family occurs in the topic,
                # or one of the topic's own words occurs in the evidence.
                alias_hits = sum(
                    1 for needle in ERROR_TOPIC_ALIASES.get(error_type, ())
                    if needle in topic_text
                )
                token_hits = sum(
                    1 for token in _topic_tokens(topic)
                    if len(token) >= 4 and token in haystack
                )
                if alias_hits == 0 and token_hits == 0:
                    continue
                score = alias_hits * 2 + token_hits + weight * 0.1
                existing = scored.get(key)
                if existing is None or score > existing["score"]:
                    scored[key] = {
                        "topic_key": key,
                        "topic": topic.get("title_it") or key,
                        "title_en": topic.get("title_en") or "",
                        "level": topic.get("level") or "",
                        "score": score,
                        "reason": str(pattern.get("label") or error_type),
                        "error_type": error_type,
                        "pattern_count": int(pattern.get("count") or 0),
                        "source": str(pattern.get("source") or ""),
                    }
    ranked = sorted(
        scored.values(),
        key=lambda entry: (-entry["score"], entry["topic_key"]),
    )
    # One recommendation per error family, strongest evidence first.
    chosen = []
    seen_types = set()
    for entry in ranked:
        if entry["error_type"] in seen_types:
            continue
        seen_types.add(entry["error_type"])
        chosen.append(entry)
        if len(chosen) >= limit:
            break
    return chosen
