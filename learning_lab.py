"""Isolated typed speaking practice for the Learning Lab.

This module is intentionally separate from the existing practice workflow.
It reads Anki data but only writes its own local history.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from practice_mode import build_practice_task, discover_practice_candidates, select_practice_targets

SCHEMA = "anki-generator-learning-lab-v1"
STATE_PATH = Path(".anki-generator", "learning-lab", "state-v1.json")

def default_state() -> dict:
    return {"schema": SCHEMA, "sessions_completed": 0, "recent_words": [], "sessions": []}

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

def select_targets(invoke_anki, state: dict, source_model: str, recall_model: str, count: int = 3) -> list[dict]:
    candidates = discover_practice_candidates(invoke_anki, source_model_name=source_model, recall_model_name=recall_model)
    return select_practice_targets(candidates, state, count=count)

def build_session(invoke_anki, state: dict, source_model: str, recall_model: str, count: int = 3) -> dict:
    targets = select_targets(invoke_anki, state, source_model, recall_model, count)
    if not targets:
        return {"targets": [], "task": None}
    return {"targets": targets, "task": build_practice_task(targets, state)}

def record_session(state: dict, targets: list[dict], *, response: str, feedback: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    result = {"at": now, "targets": [str(item.get("word")) for item in targets], "response": str(response), "feedback": feedback}
    state.setdefault("sessions", []).append(result)
    state["sessions"] = state["sessions"][-100:]
    state["sessions_completed"] = int(state.get("sessions_completed") or 0) + 1
    recent = list(state.get("recent_words") or [])
    recent.extend(result["targets"])
    state["recent_words"] = recent[-30:]
    return result
