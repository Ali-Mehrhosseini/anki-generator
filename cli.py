import os
import sys
import json
import base64
import html as html_lib
import re
import requests
import argparse
import shutil
import subprocess
import textwrap
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv

# Keep sibling modules importable when an older editable installation only
# registered this launcher module.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load environment variables from the project directory
load_dotenv(BASE_DIR / ".env")

# Import functions from the main backend
from main import (
    apply_versioned_audio_filenames,
    GEMINI_MODEL_CHAIN,
    LANGUAGE_CONFIGS,
    PRODUCTION_BACK_FIELD,
    ContextCardValidationError,
    ProductionCardValidationError,
    PRODUCTION_FRONT_FIELD,
    PRODUCTION_TEMPLATE_BACK,
    PRODUCTION_TEMPLATE_BACK_LEGACY,
    PRODUCTION_TEMPLATE_FRONT,
    PRODUCTION_TEMPLATE_MARKER,
    PRODUCTION_TEMPLATE_NAME,
    LISTENING_FIELD,
    LISTENING_TEMPLATE_NAME,
    LISTENING_TEMPLATE_MARKER,
    LISTENING_TEMPLATE_FRONT,
    LISTENING_TEMPLATE_BACK,
    CLOZE_FRONT_FIELD,
    CLOZE_BACK_FIELD,
    CLOZE_TEMPLATE_NAME,
    CLOZE_TEMPLATE_MARKER,
    CLOZE_TEMPLATE_FRONT,
    CLOZE_TEMPLATE_BACK,
    VAZIRMATN_FONT_FILES,
    create_polly_client,
    format_polly_error,
    generate_audio,
    generate_guarded_word_audio,
    generate_content,
    generate_practice_feedback,
    generate_reading_lesson,
    generate_english_meaning_audio,
    generate_word_family_audios,
    normalize_learning_features,
)
from production_backfill import (
    BackfillSafetyError,
    OWNED_MODEL_NAME,
    OWNED_TEMPLATE_BACK,
    OWNED_TEMPLATE_BACK_LEGACY,
    OWNED_TEMPLATE_FRONT,
    OWNED_TEMPLATE_NAME,
    audio_cache_is_valid,
    apply_manifest,
    apply_rollback,
    discover_candidates,
    inspect_rollback,
    inspect_owned_model_sort_field,
    load_manifest,
    prepare_manifest,
    resolve_manifest_path,
    set_owned_model_sort_field,
)
from practice_mode import (
    build_practice_task,
    create_correction_cards,
    discover_practice_candidates,
    load_practice_state,
    mark_correction_offer,
    save_practice_state,
    select_practice_targets,
    update_practice_state,
)

# Read env variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TEACH_API_KEY = os.getenv("GEMINI_TEACH_API_KEY")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
DECK_NAME = os.getenv("DECK_NAME", "Italian")
NOTE_TYPE = os.getenv("NOTE_TYPE", "Italian Vocab")
ANKI_URL = os.getenv("ANKICONNECT", "http://localhost:8765")
PRODUCTION_RECALL_DECK = f"{DECK_NAME}::Production Recall"
REQUIRED_ANKI_FIELDS = (
    "Word",
    "Front",
    "Back",
    "WordAudio",
    "Audio",
    "Conjugation",
)


def _exception_chain(error):
    """Yield an exception followed by each wrapped cause once."""
    seen = set()
    current = error

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _exception_messages(error):
    """Collect messages from an exception and its wrapped causes."""
    messages = []

    for current in _exception_chain(error):
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)

    return messages


def _format_gemini_error(error):
    """Turn Gemini/HTTP failures into concise, actionable CLI errors."""
    messages = _exception_messages(error)
    details = " | ".join(messages)
    normalized = details.casefold()
    exception_names = {
        type(item).__name__.casefold()
        for item in _exception_chain(error)
    }

    dns_markers = (
        "nodename nor servname provided",
        "name or service not known",
        "temporary failure in name resolution",
        "could not resolve host",
    )
    if any(marker in normalized for marker in dns_markers):
        return (
            "Gemini is unreachable because DNS could not resolve its API host. "
            "Check your internet connection, DNS, and VPN, then retry. No card was added."
        )

    if "connecterror" in exception_names or "connectionerror" in exception_names:
        return (
            "Could not connect to Gemini. Check your internet connection, DNS, VPN, "
            "and proxy settings, then retry. No card was added."
        )

    if (
        any("timeout" in name for name in exception_names)
        or "timeout" in normalized
        or "timed out" in normalized
    ):
        return "The Gemini request timed out. Check your connection and retry. No card was added."

    if "api_key_invalid" in normalized or "401" in normalized or "403" in normalized:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in .env and retry."

    if "resource_exhausted" in normalized or "429" in normalized:
        return "Gemini quota or rate limit was reached. Wait briefly or check your Gemini quota."

    return f"Gemini request failed: {details or type(error).__name__}"


def _generate_content_with_production_retry(*args, **kwargs):
    """Retry once when a generated card fails a recoverable validation."""
    try:
        return generate_content(*args, **kwargs)
    except (ProductionCardValidationError, ContextCardValidationError) as error:
        if isinstance(error, ContextCardValidationError):
            print(
                "↻ The card drifted away from the supplied context; "
                "regenerating it once…"
            )
        else:
            print(
                "↻ The production-recall sentence was inconsistent; "
                "regenerating the card once…"
            )
        return generate_content(*args, **kwargs)


def invoke_anki(action, params=None):
    """Call AnkiConnect API"""
    payload = {"action": action, "version": 6, "params": params or {}}
    try:
        response = requests.post(ANKI_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        if result.get("error"):
            raise Exception(result["error"])
        return result.get("result")
    except Exception as e:
        raise Exception(f"AnkiConnect error: {e}")


def ensure_anki_font_assets():
    """Install the bundled Vazirmatn files in Anki media when needed."""
    try:
        existing = set(invoke_anki(
            "getMediaFilesNames",
            {"pattern": "_Vazirmatn-*.ttf"},
        ) or [])
    except Exception as error:
        print(f"⚠️  Could not check existing Anki font media: {error}")
        existing = set()

    font_dir = os.path.join(BASE_DIR, "static", "fonts")
    for filename in VAZIRMATN_FONT_FILES:
        if filename in existing:
            continue

        font_path = os.path.join(font_dir, filename)
        try:
            with open(font_path, "rb") as font_file:
                encoded_font = base64.b64encode(font_file.read()).decode("ascii")
            invoke_anki(
                "storeMediaFile",
                {"filename": filename, "data": encoded_font},
            )
        except Exception as error:
            # Font installation is optional; keep the existing card pipeline alive.
            print(f"⚠️  Could not install {filename} in Anki media: {error}")


def _is_owned_production_template(template):
    if not isinstance(template, dict):
        return False
    front = str(template.get("Front") or "")
    back = str(template.get("Back") or "")
    return (
        PRODUCTION_TEMPLATE_MARKER in front
        and PRODUCTION_TEMPLATE_MARKER in back
        and f"{{{{#{PRODUCTION_FRONT_FIELD}}}}}" in front
        and f"{{{{{PRODUCTION_FRONT_FIELD}}}}}" in front
        and f"{{{{/{PRODUCTION_FRONT_FIELD}}}}}" in front
        and "{{FrontSide}}" in back
        and f"{{{{{PRODUCTION_BACK_FIELD}}}}}" in back
        and "{{WordAudio}}" in back
    )


def _is_canonical_production_template(template):
    if not isinstance(template, dict):
        return False
    return (
        str(template.get("Front") or "") == PRODUCTION_TEMPLATE_FRONT
        and str(template.get("Back") or "") == PRODUCTION_TEMPLATE_BACK
    )


def _is_legacy_production_template(template):
    if not isinstance(template, dict):
        return False
    return (
        str(template.get("Front") or "") == PRODUCTION_TEMPLATE_FRONT
        and str(template.get("Back") or "")
        == PRODUCTION_TEMPLATE_BACK_LEGACY
    )


def ensure_note_type(model_name):
    """Create the note type from scratch if it doesn't exist yet.

    This lets the app work on a fresh Anki install without requiring the
    user to manually create the 'Italian Vocab' note type.
    """
    existing_models = invoke_anki("modelNames") or []
    if model_name in existing_models:
        return  # Nothing to do

    print(f"📋 Note type '{model_name}' not found — creating it now…")
    invoke_anki("createModel", {
        "modelName": model_name,
        "inOrderFields": list(REQUIRED_ANKI_FIELDS),
        "css": (
            ".card {\n"
            "    font-family: arial;\n"
            "    font-size: 20px;\n"
            "    line-height: 1.5;\n"
            "    text-align: center;\n"
            "    color: black;\n"
            "    background-color: white;\n"
            "}\n"
        ),
        "cardTemplates": [
            {
                "Name": "Card 1",
                "Front": (
                    "<div style='font-family: \"Arial\"; font-size: 20px;'>"
                    "{{Front}}</div>\n"
                    "<div style='font-family: \"Arial\"; font-size: 20px;'>"
                    "{{WordAudio}}</div>"
                ),
                "Back": (
                    "{{FrontSide}}\n\n"
                    "<hr id=answer>\n\n"
                    "<div style='font-family: \"Arial\"; font-size: 20px;'>"
                    "{{Back}}</div>"
                ),
            }
        ],
    })
    print(f"✅ Note type '{model_name}' created.")


def ensure_production_card_model(model_name):
    """Safely add the app-owned conditional production card type."""
    # Auto-create the note type if this is a fresh Anki install.
    ensure_note_type(model_name)

    initial_fields = invoke_anki(
        "modelFieldNames",
        {"modelName": model_name},
    )
    missing_required = [
        field
        for field in REQUIRED_ANKI_FIELDS
        if field not in initial_fields
    ]
    if missing_required:
        raise ValueError(
            f"Note type '{model_name}' is missing: "
            f"{', '.join(missing_required)}"
        )

    initial_templates = invoke_anki(
        "modelTemplates",
        {"modelName": model_name},
    )
    existing = (initial_templates or {}).get(PRODUCTION_TEMPLATE_NAME)
    if existing and not _is_owned_production_template(existing):
        raise ValueError(
            f"Note type '{model_name}' already has a card type named "
            f"'{PRODUCTION_TEMPLATE_NAME}' that is not owned by this app."
        )
    if (
        existing
        and not _is_canonical_production_template(existing)
        and not _is_legacy_production_template(existing)
    ):
        raise ValueError(
            f"The app-owned '{PRODUCTION_TEMPLATE_NAME}' card type was "
            "edited or is outdated. Remove it in Settings, then try again."
        )

    if existing and _is_legacy_production_template(existing):
        invoke_anki(
            "updateModelTemplates",
            {
                "model": {
                    "name": model_name,
                    "templates": {
                        PRODUCTION_TEMPLATE_NAME: {
                            "Front": PRODUCTION_TEMPLATE_FRONT,
                            "Back": PRODUCTION_TEMPLATE_BACK,
                        },
                    },
                },
            },
        )
        existing = {
            "Front": PRODUCTION_TEMPLATE_FRONT,
            "Back": PRODUCTION_TEMPLATE_BACK,
        }

    has_production_field = any(
        field in initial_fields
        for field in (PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD)
    )
    if not existing and has_production_field:
        raise ValueError(
            f"Note type '{model_name}' already contains a production field "
            "with the same name. Nothing was changed."
        )

    added_fields = []
    template_added = False

    def rollback_new_model_parts():
        if template_added:
            try:
                invoke_anki(
                    "modelTemplateRemove",
                    {
                        "modelName": model_name,
                        "templateName": PRODUCTION_TEMPLATE_NAME,
                    },
                )
            except Exception:
                pass
        for field_name in reversed(added_fields):
            try:
                invoke_anki(
                    "modelFieldRemove",
                    {"modelName": model_name, "fieldName": field_name},
                )
            except Exception:
                pass

    try:
        for field_name in (PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD):
            if field_name not in initial_fields:
                invoke_anki(
                    "modelFieldAdd",
                    {"modelName": model_name, "fieldName": field_name},
                )
                added_fields.append(field_name)

        if not existing:
            invoke_anki(
                "modelTemplateAdd",
                {
                    "modelName": model_name,
                    "template": {
                        "Name": PRODUCTION_TEMPLATE_NAME,
                        "Front": PRODUCTION_TEMPLATE_FRONT,
                        "Back": PRODUCTION_TEMPLATE_BACK,
                    },
                },
            )
            template_added = True
    except Exception:
        rollback_new_model_parts()
        raise

    try:
        verified_fields = invoke_anki(
            "modelFieldNames",
            {"modelName": model_name},
        )
        verified_templates = invoke_anki(
            "modelTemplates",
            {"modelName": model_name},
        )
    except Exception:
        rollback_new_model_parts()
        raise
    fields_ready = all(
        field in verified_fields
        for field in (PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD)
    )
    template_ready = _is_canonical_production_template(
        (verified_templates or {}).get(PRODUCTION_TEMPLATE_NAME)
    )
    if not fields_ready or not template_ready:
        rollback_new_model_parts()
        raise RuntimeError(
            "Anki did not finish creating the production card type. "
            "Update AnkiConnect or use --no-production-card."
        )


def _is_owned_listening_template(template):
    if not template:
        return False
    front = str(template.get("Front") or "")
    back = str(template.get("Back") or "")
    return (
        LISTENING_TEMPLATE_MARKER in front
        and LISTENING_TEMPLATE_MARKER in back
    )


def _ensure_listening_card_model(model_name, initial_fields):
    """Add the Listening Comprehension template and field to the note type."""
    initial_templates = invoke_anki(
        "modelTemplates",
        {"modelName": model_name},
    )
    existing = (initial_templates or {}).get(LISTENING_TEMPLATE_NAME)
    if existing and not _is_owned_listening_template(existing):
        raise ValueError(
            f"Note type '{model_name}' already has a card type named "
            f"'{LISTENING_TEMPLATE_NAME}' that is not owned by this app."
        )

    has_field = LISTENING_FIELD in initial_fields
    if not existing and has_field:
        raise ValueError(
            f"Note type '{model_name}' already contains a listening field "
            "with the same name. Nothing was changed."
        )

    added_fields = []
    template_added = False

    def rollback():
        if template_added:
            try:
                invoke_anki(
                    "modelTemplateRemove",
                    {
                        "modelName": model_name,
                        "templateName": LISTENING_TEMPLATE_NAME,
                    },
                )
            except Exception:
                pass
        for field_name in reversed(added_fields):
            try:
                invoke_anki(
                    "modelFieldRemove",
                    {"modelName": model_name, "fieldName": field_name},
                )
            except Exception:
                pass

    try:
        if LISTENING_FIELD not in initial_fields:
            invoke_anki(
                "modelFieldAdd",
                {"modelName": model_name, "fieldName": LISTENING_FIELD},
            )
            added_fields.append(LISTENING_FIELD)

        if not existing:
            invoke_anki(
                "modelTemplateAdd",
                {
                    "modelName": model_name,
                    "template": {
                        "Name": LISTENING_TEMPLATE_NAME,
                        "Front": LISTENING_TEMPLATE_FRONT,
                        "Back": LISTENING_TEMPLATE_BACK,
                    },
                },
            )
            template_added = True
    except Exception:
        rollback()
        raise

    try:
        verified_fields = invoke_anki(
            "modelFieldNames",
            {"modelName": model_name},
        )
        verified_templates = invoke_anki(
            "modelTemplates",
            {"modelName": model_name},
        )
    except Exception:
        rollback()
        raise
    if LISTENING_FIELD not in verified_fields:
        rollback()
        raise RuntimeError(
            "Anki did not finish creating the listening card type."
        )
    if not _is_owned_listening_template(
        (verified_templates or {}).get(LISTENING_TEMPLATE_NAME)
    ):
        rollback()
        raise RuntimeError(
            "Anki did not finish creating the listening card type."
        )


def _is_owned_cloze_template(template):
    if not template:
        return False
    front = str(template.get("Front") or "")
    back = str(template.get("Back") or "")
    return (
        CLOZE_TEMPLATE_MARKER in front
        and CLOZE_TEMPLATE_MARKER in back
    )


def _ensure_cloze_card_model(model_name, initial_fields):
    """Add the Sentence Cloze template and fields to the note type."""
    initial_templates = invoke_anki(
        "modelTemplates",
        {"modelName": model_name},
    )
    existing = (initial_templates or {}).get(CLOZE_TEMPLATE_NAME)
    if existing and not _is_owned_cloze_template(existing):
        raise ValueError(
            f"Note type '{model_name}' already has a card type named "
            f"'{CLOZE_TEMPLATE_NAME}' that is not owned by this app."
        )

    has_field = any(
        field in initial_fields
        for field in (CLOZE_FRONT_FIELD, CLOZE_BACK_FIELD)
    )
    if not existing and has_field:
        raise ValueError(
            f"Note type '{model_name}' already contains a cloze field "
            "with the same name. Nothing was changed."
        )

    added_fields = []
    template_added = False

    def rollback():
        if template_added:
            try:
                invoke_anki(
                    "modelTemplateRemove",
                    {
                        "modelName": model_name,
                        "templateName": CLOZE_TEMPLATE_NAME,
                    },
                )
            except Exception:
                pass
        for field_name in reversed(added_fields):
            try:
                invoke_anki(
                    "modelFieldRemove",
                    {"modelName": model_name, "fieldName": field_name},
                )
            except Exception:
                pass

    try:
        for field_name in (CLOZE_FRONT_FIELD, CLOZE_BACK_FIELD):
            if field_name not in initial_fields:
                invoke_anki(
                    "modelFieldAdd",
                    {"modelName": model_name, "fieldName": field_name},
                )
                added_fields.append(field_name)

        if not existing:
            invoke_anki(
                "modelTemplateAdd",
                {
                    "modelName": model_name,
                    "template": {
                        "Name": CLOZE_TEMPLATE_NAME,
                        "Front": CLOZE_TEMPLATE_FRONT,
                        "Back": CLOZE_TEMPLATE_BACK,
                    },
                },
            )
            template_added = True
    except Exception:
        rollback()
        raise

    try:
        verified_fields = invoke_anki(
            "modelFieldNames",
            {"modelName": model_name},
        )
        verified_templates = invoke_anki(
            "modelTemplates",
            {"modelName": model_name},
        )
    except Exception:
        rollback()
        raise
    fields_ready = all(
        field in verified_fields
        for field in (CLOZE_FRONT_FIELD, CLOZE_BACK_FIELD)
    )
    if not fields_ready or not _is_owned_cloze_template(
        (verified_templates or {}).get(CLOZE_TEMPLATE_NAME)
    ):
        rollback()
        raise RuntimeError(
            "Anki did not finish creating the sentence cloze card type."
        )

def _anki_search_literal(value):
    """Quote a value for Anki's search syntax."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"')

def _normalize_duplicate_value(value):
    return str(value or "").strip().casefold()

def check_duplicate(word, deck_name, field_name="Word"):
    """Check if the word already exists in the deck's primary word field."""
    try:
        escaped_deck = _anki_search_literal(deck_name)
        escaped_word = _anki_search_literal(word)
        field_query = f'deck:"{escaped_deck}" {field_name}:"{escaped_word}"'
        notes = invoke_anki("findNotes", {"query": field_query})

        # If Anki's field search misses because of search syntax/version quirks,
        # scan the deck and still compare only the configured main word field.
        if not notes:
            deck_query = f'deck:"{escaped_deck}"'
            notes = invoke_anki("findNotes", {"query": deck_query})

        if not notes:
            return False

        notes_info = invoke_anki("notesInfo", {"notes": notes})
        target = _normalize_duplicate_value(word)
        for note in notes_info:
            field = note.get("fields", {}).get(field_name, {})
            if _normalize_duplicate_value(field.get("value")) == target:
                return True
        return False
    except Exception as e:
        print(f"Warning: Duplicate check failed. Is Anki open and AnkiConnect installed? Error: {e}")
        # Return False to let it continue if there's an issue checking, or user can abort.
        return False


def get_duplicate_form_explanation(typed_word, generated_word, data):
    """Extract the model's note explaining how an input maps to its lemma."""
    typed = str(typed_word or "").strip()
    lemma = str(generated_word or typed).strip()
    if typed.casefold() == lemma.casefold():
        return (
            f"'{typed}' is already the dictionary form stored by the app."
        )

    smart_grammar = (data or {}).get("smart_grammar") or {}
    past_participle = str(
        smart_grammar.get("past_participle") or ""
    ).strip()
    if past_participle and typed.casefold() == past_participle.casefold():
        return (
            f"'{typed}' is the past participle of '{lemma}' "
            "(used in compound tenses and passive constructions), "
            "not a separate verb."
        )

    back_html = str((data or {}).get("back_html") or "")
    notes = re.findall(
        r"<li\b[^>]*>(.*?)</li>",
        back_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for note_html in notes:
        plain = re.sub(r"<[^>]+>", " ", note_html)
        plain = html_lib.unescape(plain)
        plain = " ".join(plain.split())
        if typed.casefold() in plain.casefold():
            return plain

    return (
        f"'{typed}' was recognized as a form or attached-pronoun use of "
        f"the dictionary word '{lemma}', not as a separate base word."
    )


def print_duplicate_form_explanation(typed_word, generated_word, data):
    explanation = get_duplicate_form_explanation(
        typed_word,
        generated_word,
        data,
    )
    print("ℹ️  Why no new card was created:")
    print(f"   {explanation}")
    print(
        f"   The app stores the main card under '{generated_word}', "
        "and that card already exists."
    )


def choose_interpretation_cli(
    word,
    options,
    input_func=None,
    interactive=None,
):
    """Show numbered meanings and return the user's selected interpretation."""
    choices = [option for option in (options or []) if isinstance(option, dict)]
    if len(choices) < 2:
        print("❌ The possible meanings could not be identified clearly.")
        return None

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print(
            "❌ This word has multiple meanings and needs an interactive choice. "
            "Run the command in a terminal, or add a short meaning/context to the input."
        )
        return None

    print(f"\n🔀 '{word}' has more than one possible interpretation:")
    for index, option in enumerate(choices, start=1):
        headword = str(option.get("headword") or word).strip()
        part = str(option.get("part_of_speech") or "other").strip()
        meaning_en = str(option.get("meaning_en") or "").strip()
        meaning_fa = str(option.get("meaning_fa") or "").strip()
        explanation = str(option.get("explanation") or "").strip()
        print(f"  {index}) {headword} [{part}] — {meaning_en}")
        if meaning_fa:
            print(f"     Persian: {meaning_fa}")
        if explanation:
            print(f"     {explanation}")

    reader = input_func or input
    while True:
        answer = reader(
            f"Choose 1-{len(choices)}, a for all (or q to cancel): "
        ).strip().lower()
        if answer in {"q", "quit", "cancel"}:
            print("Cancelled; no card or audio was created.")
            return None
        if answer in {"a", "all", "both"}:
            print(
                "✓ Selected all: "
                + ", ".join(
                    str(choice.get("headword") or word)
                    for choice in choices
                )
            )
            return choices
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            selected = choices[int(answer) - 1]
            print(
                "✓ Selected: "
                f"{selected.get('headword')} — {selected.get('meaning_en')}"
            )
            return selected
        print(f"Please enter a number from 1 to {len(choices)}, or q.")

def add_word_to_anki(
    word,
    language,
    custom_prompt=None,
    translation_lang="Both (English + Persian)",
    feature_options=None,
    selected_interpretation=None,
    usage_context=None,
    gemini_api_key=None,
):
    """Full pipeline for a single word"""
    print(f"--- Processing: {word} ---")
    features = normalize_learning_features(feature_options, language)

    if selected_interpretation:
        print(
            "🧠 Creating the selected card for "
            f"'{selected_interpretation.get('headword')}'..."
        )
    else:
        print(f"🧠 Asking Gemini to translate '{word}'...")
    if usage_context:
        print("📎 Using the supplied context to determine the intended meaning.")
    active_gemini_key = gemini_api_key or GEMINI_API_KEY
    try:
        data = _generate_content_with_production_retry(
            word,
            language,
            active_gemini_key,
            custom_prompt,
            translation_lang,
            feature_options=features,
            enable_disambiguation=True,
            selected_interpretation=selected_interpretation,
            usage_context=usage_context,
        )
    except Exception as e:
        print(f"❌ {_format_gemini_error(e)}")
        return False
    
    if data.get("error"):
        print(f"❌ Gemini Error: {data['error']}")
        return False

    if data.get("needs_disambiguation"):
        selected = choose_interpretation_cli(
            word,
            data.get("interpretations"),
        )
        if not selected:
            return False

        if isinstance(selected, list):
            print(
                f"\n📚 Creating {len(selected)} separate cards for '{word}'..."
            )
            results = []
            for option in selected:
                results.append(add_word_to_anki(
                    word,
                    language,
                    custom_prompt=custom_prompt,
                    translation_lang=translation_lang,
                    feature_options=features,
                    selected_interpretation=option,
                    usage_context=usage_context,
                    gemini_api_key=active_gemini_key,
                ))
            added = sum(bool(result) for result in results)
            print(
                f"📚 Added {added} of {len(selected)} selected cards for '{word}'."
            )
            return added == len(selected)

        print(
            "🧠 Creating the selected card for "
            f"'{selected.get('headword')}'..."
        )
        try:
            data = _generate_content_with_production_retry(
                word,
                language,
                active_gemini_key,
                custom_prompt,
                translation_lang,
                feature_options=features,
                enable_disambiguation=True,
                selected_interpretation=selected,
                usage_context=usage_context,
            )
        except Exception as e:
            print(f"❌ {_format_gemini_error(e)}")
            return False

        if data.get("error"):
            print(f"❌ Gemini Error: {data['error']}")
            return False

    production_card = data.get("production_card_html") or {}
    if (
        features["production_card"]
        and not (
            production_card.get("front_html")
            and production_card.get("back_html")
        )
    ):
        print(
            "❌ Production recall was enabled, but its sentence could not "
            "be verified. Nothing was added; please try again."
        )
        return False

    generated_word = data.get("word", word)
    gemini_model = data.get("_gemini_model") or "unknown"
    print(f"🤖 Card generated with: {gemini_model}")
    if usage_context:
        contextual_meaning = str(
            data.get("tts_meaning_en") or ""
        ).strip()
        if contextual_meaning:
            print(f"🧭 Meaning in this context: {contextual_meaning}")
        print(f"   Dictionary form: {generated_word}")
    if check_duplicate(generated_word, DECK_NAME):
        print(f"⏭️  Skipping '{generated_word}', already exists as a main word in deck '{DECK_NAME}'.")
        print_duplicate_form_explanation(word, generated_word, data)
        return False


    if features["production_card"]:
        try:
            ensure_production_card_model(NOTE_TYPE)
        except Exception as error:
            print(
                "❌ Production card setup failed: "
                f"{error} Turn it off with --no-production-card."
            )
            return False

    if features.get("listening_card"):
        try:
            initial_fields = invoke_anki(
                "modelFieldNames",
                {"modelName": NOTE_TYPE},
            )
            _ensure_listening_card_model(NOTE_TYPE, initial_fields)
        except Exception as error:
            print(
                "❌ Listening card setup failed: "
                f"{error} Turn it off with --no-listening-card."
            )
            return False

    if features.get("sentence_cloze"):
        try:
            initial_fields = invoke_anki(
                "modelFieldNames",
                {"modelName": NOTE_TYPE},
            )
            _ensure_cloze_card_model(NOTE_TYPE, initial_fields)
        except Exception as error:
            print(
                "❌ Cloze card setup failed: "
                f"{error} Turn it off with --no-sentence-cloze."
            )
            return False

    config = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["Italian"])
    voice = config["voice"]
    lang_code = config["code"]
    engine = config.get("engine", "neural")
    is_verb = bool(data.get("conjugation_field"))

    print(f"🗣️  Synthesizing audio with AWS Polly...")
    aws_kwargs = {
        "aws_access_key": AWS_ACCESS_KEY,
        "aws_secret_key": AWS_SECRET_KEY,
        "engine": engine,
    }

    try:
        aws_kwargs["polly_client"] = create_polly_client(
            AWS_ACCESS_KEY,
            AWS_SECRET_KEY,
        )
        audios = {
            "":         generate_guarded_word_audio(data["tts_word"], voice, lang_code, **aws_kwargs),
            "_example": generate_audio(data["tts_example"], voice, lang_code, **aws_kwargs),
        }
        if is_verb:
            for i in range(1, 7):
                audios[f"_{i}"] = generate_audio(data[f"tts_verb_{i}"], voice, lang_code, **aws_kwargs)
        audios.update(generate_english_meaning_audio(data, **aws_kwargs))
        audios.update(generate_word_family_audios(data, voice, lang_code, **aws_kwargs))
        audio_filenames = apply_versioned_audio_filenames(data, audios)
    except Exception as e:
        print(f"❌ AWS Polly Error: {format_polly_error(e)}")
        return False

    print(f"📦 Compiling and sending to Anki...")
    
    try:
        # Create Deck if not exists
        decks = invoke_anki('deckNames')
        if DECK_NAME not in decks:
            invoke_anki('createDeck', {'deck': DECK_NAME})

        if "AnkiVazirmatn" in data.get("back_html", ""):
            ensure_anki_font_assets()

        # Store media files
        for suffix, audio_bytes in audios.items():
            filename = audio_filenames[suffix]
            b64_data = base64.b64encode(audio_bytes).decode('utf-8')
            invoke_anki('storeMediaFile', {'filename': filename, 'data': b64_data})

        fields = {
            "Word": data['word'],
            "Front": data['front_html'],
            "Back": data['back_html'],
            "WordAudio": f"[sound:{audio_filenames['']}]",
            # The example is rendered as a manual HTML5 control in Back.
            "Audio": "",
            "Conjugation": data['conjugation_field'],
        }
        production_card = data.get("production_card_html") or {}
        if (
            features["production_card"]
            and production_card.get("front_html")
            and production_card.get("back_html")
        ):
            fields[PRODUCTION_FRONT_FIELD] = production_card["front_html"]
            fields[PRODUCTION_BACK_FIELD] = production_card["back_html"]

        # Listening: a non-empty marker activates the conditional template.
        if features.get("listening_card") and data.get("listening_enabled"):
            fields[LISTENING_FIELD] = "1"

        # Cloze: populate with the generated cloze HTML.
        cloze_card = data.get("cloze_card_html") or {}
        if (
            features.get("sentence_cloze")
            and cloze_card.get("front_html")
            and cloze_card.get("back_html")
        ):
            fields[CLOZE_FRONT_FIELD] = cloze_card["front_html"]
            fields[CLOZE_BACK_FIELD] = cloze_card["back_html"]

        # Add one note; the conditional template creates the optional sibling card.
        note_params = {
            "note": {
                "deckName": DECK_NAME,
                "modelName": NOTE_TYPE,
                "fields": fields,
                "tags": ["auto", language.lower(), "cli"],
                "options": {"allowDuplicate": True}
            }
        }
    
        note_id = invoke_anki('addNote', note_params)
        card_types = ["recognition"]
        if PRODUCTION_FRONT_FIELD in fields:
            card_types.append("production")
        if LISTENING_FIELD in fields:
            card_types.append("listening")
        if CLOZE_FRONT_FIELD in fields:
            card_types.append("cloze")
        card_summary = " + ".join(card_types) + (
            " cards" if len(card_types) > 1 else " card"
        )
        print(
            f"✅ Successfully added '{generated_word}' ({card_summary})! "
            f"Note ID: {note_id}"
        )
        return True
        
    except Exception as e:
        print(f"❌ Error adding note: {e}")
        return False


def read_clipboard_text(run_func=None):
    """Read the macOS clipboard without using a shell or changing it."""
    runner = run_func or subprocess.run
    try:
        result = runner(
            ["pbpaste"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "Automatic clipboard reading currently requires macOS `pbpaste`."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Reading the clipboard timed out.") from error

    if result.returncode != 0:
        detail = str(result.stderr or "").strip()
        raise RuntimeError(
            "The clipboard could not be read"
            + (f": {detail}" if detail else ".")
        )
    text = str(result.stdout or "").strip()
    if not text:
        raise ValueError(
            "The clipboard is empty. Copy an Italian sentence or article first."
        )
    return text


def _safe_lesson_entries(value):
    return [item for item in (value or []) if isinstance(item, dict)]


def _terminal_text_width():
    """Keep lesson text readable even in an extra-wide terminal window."""
    columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    return max(48, min(92, columns - 4))


def _terminal_uses_color():
    """Use a restrained palette only for an interactive capable terminal."""
    if os.getenv("NO_COLOR") is not None:
        return False
    return (
        sys.stdout.isatty()
        and os.getenv("TERM", "").strip().lower() != "dumb"
    )


def _terminal_style(value, *codes):
    """Apply ANSI styling without leaking escape codes into redirected output."""
    text = str(value)
    if not codes or not _terminal_uses_color():
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def _clean_terminal_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _print_wrapped(value, *, first="", rest=None, style=()):
    """Print one value with stable indentation and a readable line length."""
    text = _clean_terminal_text(value)
    if not text:
        return
    subsequent = first if rest is None else rest
    rendered = textwrap.fill(
        text,
        width=_terminal_text_width(),
        initial_indent=first,
        subsequent_indent=subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if style:
        rendered = "\n".join(
            _terminal_style(line, *style)
            for line in rendered.splitlines()
        )
    print(rendered)


def _print_lesson_heading(label):
    title = f" {label.upper()} "
    rule = "──" + title
    rule += "─" * max(0, _terminal_text_width() - len(rule))
    print("\n" + _terminal_style(rule, "1", "36"))


def _can_show_iterm_persian_image():
    """Return whether Persian can be rendered as a Vazirmatn iTerm image."""
    mode = os.getenv("ANKI_TEACH_PERSIAN_MODE", "text").strip().lower()
    return (
        os.getenv("TERM_PROGRAM") == "iTerm.app"
        and sys.stdout.isatty()
        and mode == "image"
    )


def _render_persian_png(text, *, width=1120):
    """Render correctly joined RTL Persian with bundled Vazirmatn."""
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display

    font_path = BASE_DIR / "static" / "fonts" / "_Vazirmatn-Regular.ttf"
    font = ImageFont.truetype(str(font_path), 23)
    padding_x = 34
    padding_y = 24
    line_gap = 15
    max_text_width = width - (padding_x * 2)
    measure_image = Image.new("RGBA", (1, 1))
    measure = ImageDraw.Draw(measure_image)

    def visual(value):
        return get_display(arabic_reshaper.reshape(value))

    logical_lines = []
    current_words = []
    for word in _clean_terminal_text(text).split():
        candidate_words = current_words + [word]
        candidate = " ".join(candidate_words)
        bounds = measure.textbbox((0, 0), visual(candidate), font=font)
        if current_words and bounds[2] - bounds[0] > max_text_width:
            logical_lines.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words = candidate_words
    if current_words:
        logical_lines.append(" ".join(current_words))
    if not logical_lines:
        logical_lines = [""]

    sample_bounds = measure.textbbox((0, 0), "ایران", font=font)
    line_height = sample_bounds[3] - sample_bounds[1]
    height = (
        padding_y * 2
        + (line_height * len(logical_lines))
        + (line_gap * max(0, len(logical_lines) - 1))
    )
    image = Image.new("RGBA", (width, height), (31, 34, 42, 255))
    draw = ImageDraw.Draw(image)
    y = padding_y - sample_bounds[1]
    for line in logical_lines:
        draw.text(
            (width - padding_x, y),
            visual(line),
            font=font,
            fill=(246, 246, 248, 255),
            anchor="ra",
        )
        y += line_height + line_gap

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _print_iterm_persian_image(text):
    """Display one Persian paragraph using iTerm's inline-image protocol."""
    try:
        png = _render_persian_png(text)
    except (ImportError, OSError, ValueError):
        return False
    encoded = base64.b64encode(png).decode("ascii")
    width = max(20, _terminal_text_width() - 8)
    print(
        f"\033]1337;File=inline=1;width={width};height=auto;"
        f"preserveAspectRatio=1:{encoded}\a"
    )
    return True


def _print_lesson_field(label, value, *, indent="    "):
    text = _clean_terminal_text(value)
    if not text:
        return
    display_label = label.upper()
    label_style = ("36",)
    if label.casefold() == "persian":
        if _can_show_iterm_persian_image():
            display_label += " · VAZIRMATN IMAGE"
        print(_terminal_style(f"{indent}{display_label}", *label_style))
        if _can_show_iterm_persian_image() and _print_iterm_persian_image(text):
            return
        # Default: original selectable Unicode text. iTerm handles RTL and
        # cursive shaping when RTL support and Ligatures are enabled.
        rtl_indent = indent + "  "
        _print_wrapped(text, first=rtl_indent, rest=rtl_indent)
        return

    label_width = 9
    prefix = f"{indent}{display_label:<{label_width}}"
    content_width = max(20, _terminal_text_width() - len(prefix))
    lines = textwrap.wrap(
        text,
        width=content_width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    print(_terminal_style(prefix, *label_style) + lines[0])
    continuation = " " * len(prefix)
    for line in lines[1:]:
        print(continuation + line)


def _print_lesson_subheading(label):
    print("\n" + _terminal_style(f"    {label.upper()}", "1", "36"))


def _print_story_parts(parts):
    """Render a complete local deep dive for each ordered story part."""
    all_items = []
    total_parts = len(parts)
    item_number = 1

    for part_index, part in enumerate(parts, start=1):
        part_title = str(
            part.get("part_title") or f"Story part {part_index}"
        ).strip()
        _print_lesson_heading(
            f"Part {part_index} of {total_parts} · {part_title}"
        )
        _print_lesson_field("Italian", part.get("source_text"))
        _print_lesson_field("English", part.get("translation_en"))
        _print_lesson_field("Persian", part.get("translation_fa"))
        _print_lesson_field("Focus", part.get("learning_focus"))

        items = _safe_lesson_entries(part.get("learning_items"))
        if items:
            _print_lesson_subheading("Words and expressions")
            for local_index, item in enumerate(items):
                term = str(
                    item.get("term") or item.get("card_target") or ""
                ).strip()
                word_class = str(
                    item.get("part_of_speech") or item.get("kind") or ""
                ).strip()
                heading = term + (
                    f" · {word_class}" if word_class else ""
                )
                number = f"{item_number:02d}  "
                _print_wrapped(
                    heading,
                    first=number,
                    rest=" " * len(number),
                    style=("1",),
                )
                _print_lesson_field("English", item.get("meaning_en"))
                _print_lesson_field("Persian", item.get("meaning_fa"))
                _print_lesson_field("Note", item.get("teaching_note"))
                _print_lesson_field("In text", item.get("source_excerpt"))
                all_items.append(item)
                item_number += 1
                if local_index + 1 < len(items):
                    print()

        grammar = _safe_lesson_entries(part.get("grammar_points"))
        if grammar:
            _print_lesson_subheading("Grammar in this part")
            for grammar_index, point in enumerate(grammar, start=1):
                number = f"G{grammar_index}  "
                _print_wrapped(
                    point.get("pattern") or "Grammar point",
                    first=number,
                    rest=" " * len(number),
                    style=("1",),
                )
                _print_lesson_field("English", point.get("explanation_en"))
                _print_lesson_field("Persian", point.get("explanation_fa"))
                _print_lesson_field("Example", point.get("source_excerpt"))
                if grammar_index < len(grammar):
                    print()

        questions = _safe_lesson_entries(
            part.get("comprehension_questions")
        )
        if questions:
            _print_lesson_subheading("Check this part")
            for question_index, question in enumerate(questions, start=1):
                number = f"Q{question_index}  "
                _print_wrapped(
                    question.get("question_it") or "Question",
                    first=number,
                    rest=" " * len(number),
                    style=("1",),
                )
                _print_lesson_field("English", question.get("answer_en"))
                _print_lesson_field("Persian", question.get("answer_fa"))
                if question_index < len(questions):
                    print()

    return all_items


def print_reading_lesson(lesson):
    """Render a structured lesson with readable terminal hierarchy."""
    title = str(lesson.get("title") or "Reading lesson").strip()
    difficulty = str(lesson.get("difficulty") or "?").strip()
    parts = _safe_lesson_entries(lesson.get("parts"))
    width = _terminal_text_width()
    banner = " READING LESSON "
    top = "╭─" + banner
    top += "─" * max(0, width - len(top))
    print("\n" + _terminal_style(top, "1", "36"))
    _print_wrapped(title, first="│  ", rest="│  ", style=("1",))
    lesson_detail = f"Level {difficulty}"
    if parts:
        lesson_detail += f" · {len(parts)} story part(s)"
    print(_terminal_style(f"│  {lesson_detail}", "36"))
    print(_terminal_style("╰" + "─" * (width - 1), "36"))

    if parts:
        items = _print_story_parts(parts)
        print("\n" + _terminal_style("─" * width, "36"))
        return items

    summary_en = str(lesson.get("summary_en") or "").strip()
    summary_fa = str(lesson.get("summary_fa") or "").strip()
    if summary_en or summary_fa:
        _print_lesson_heading("Overview")
        _print_lesson_field("English", summary_en)
        _print_lesson_field("Persian", summary_fa)

    sections = _safe_lesson_entries(lesson.get("section_explanations"))
    if sections:
        _print_lesson_heading("Guided reading · section by section")
        for index, section in enumerate(sections, start=1):
            excerpt = str(section.get("source_excerpt") or "").strip()
            explanation_en = str(
                section.get("explanation_en") or ""
            ).strip()
            explanation_fa = str(
                section.get("explanation_fa") or ""
            ).strip()
            focus = str(section.get("learning_focus") or "").strip()
            number = f"{index:02d}  "
            _print_wrapped(
                excerpt or "Section",
                first=number,
                rest=" " * len(number),
                style=("1",),
            )
            _print_lesson_field("English", explanation_en)
            _print_lesson_field("Persian", explanation_fa)
            _print_lesson_field("Focus", focus)
            if index != len(sections):
                print()

    items = _safe_lesson_entries(lesson.get("learning_items"))
    if items:
        _print_lesson_heading("Important words and expressions")
        for index, item in enumerate(items, start=1):
            term = str(item.get("term") or item.get("card_target") or "").strip()
            part = str(item.get("part_of_speech") or item.get("kind") or "").strip()
            meaning_en = str(item.get("meaning_en") or "").strip()
            meaning_fa = str(item.get("meaning_fa") or "").strip()
            note = str(item.get("teaching_note") or "").strip()
            excerpt = str(item.get("source_excerpt") or "").strip()
            heading = term + (f"  ·  {part}" if part else "")
            number = f"{index:02d}  "
            _print_wrapped(
                heading,
                first=number,
                rest=" " * len(number),
                style=("1",),
            )
            _print_lesson_field("English", meaning_en)
            _print_lesson_field("Persian", meaning_fa)
            _print_lesson_field("Note", note)
            _print_lesson_field("In text", excerpt)
            if index != len(items):
                print()

    grammar = _safe_lesson_entries(lesson.get("grammar_points"))
    if grammar:
        _print_lesson_heading("Grammar worth noticing")
        for index, point in enumerate(grammar, start=1):
            pattern = str(point.get("pattern") or "").strip()
            explanation = str(point.get("explanation_en") or "").strip()
            excerpt = str(point.get("source_excerpt") or "").strip()
            number = f"{index:02d}  "
            _print_wrapped(
                pattern,
                first=number,
                rest=" " * len(number),
                style=("1",),
            )
            _print_lesson_field("Meaning", explanation)
            _print_lesson_field("Example", excerpt)
            if index != len(grammar):
                print()

    questions = _safe_lesson_entries(
        lesson.get("comprehension_questions")
    )
    if questions:
        _print_lesson_heading("Check your understanding")
        for index, question in enumerate(questions, start=1):
            text = str(question.get("question_it") or "").strip()
            answer = str(question.get("answer_en") or "").strip()
            number = f"{index:02d}  "
            _print_wrapped(
                text,
                first=number,
                rest=" " * len(number),
                style=("1",),
            )
            _print_lesson_field("Answer", answer)
            if index != len(questions):
                print()

    print("\n" + _terminal_style("─" * width, "36"))

    return items


def choose_lesson_items_cli(
    items,
    input_func=None,
    interactive=None,
):
    """Return only explicitly selected lesson items."""
    choices = _safe_lesson_entries(items)
    if not choices:
        print("\nNo suitable card suggestions were found.")
        return []
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print("\nLesson complete. No cards were added in non-interactive mode.")
        return []

    reader = input_func or input
    _print_lesson_heading("Create cards · optional")
    print("Anki is still unchanged. Add only the items you want to study.")
    print(_terminal_style(
        "Numbers: 1,3,5    All: a    Finish without cards: q",
        "36",
    ))
    while True:
        answer = reader("\nAdd cards › ").strip().lower()
        if answer in {"q", "quit", "none", "no"}:
            print("Lesson complete; no cards were added.")
            return []
        if answer in {"a", "all"}:
            return choices

        tokens = [token for token in re.split(r"[\s,]+", answer) if token]
        if tokens and all(token.isdigit() for token in tokens):
            indexes = []
            for token in tokens:
                index = int(token)
                if not 1 <= index <= len(choices):
                    break
                if index not in indexes:
                    indexes.append(index)
            else:
                return [choices[index - 1] for index in indexes]
        print(
            f"Choose numbers from 1–{len(choices)}, "
            "a for all, or q to finish."
        )


def _run_teacher_cli(args):
    """Create a clipboard lesson, then optionally use the normal card flow."""
    try:
        source_text = read_clipboard_text()
    except (RuntimeError, ValueError) as error:
        print(f"❌ {error}")
        return 1

    word_count = len(re.findall(r"\b\w+\b", source_text, re.UNICODE))
    line_count = sum(
        1 for line in source_text.splitlines() if line.strip()
    ) or 1
    print("\n" + _terminal_style("ANKI TEACH", "1", "36"))
    print(_terminal_style("─" * _terminal_text_width(), "36"))
    print(f"Source    {word_count:,} words · {line_count:,} text lines")
    print("Anki      No changes until you select cards")
    try:
        _require_generation_keys(gemini=False, aws=False, teach=True)
        teacher_gemini_key = GEMINI_TEACH_API_KEY or GEMINI_API_KEY
        if GEMINI_TEACH_API_KEY:
            print("Account   Dedicated Gemini teaching key")
        else:
            print("Account   Normal Gemini key (no teaching key configured)")
        print(f"Model     {GEMINI_MODEL_CHAIN[0]} first · automatic fallback")
        print("Status    Creating your lesson…  (Ctrl-C cancels safely)")
        lesson = generate_reading_lesson(
            source_text,
            args.language,
            teacher_gemini_key,
        )
    except KeyboardInterrupt:
        print("\n\nCancelled — Anki was not changed.")
        return 130
    except (BackfillSafetyError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    except Exception as error:
        print(f"❌ {_format_gemini_error(error)}")
        return 1

    if lesson.get("error"):
        print(f"❌ Gemini Error: {lesson['error']}")
        return 1

    model = str(lesson.get("_gemini_model") or "unknown")
    print(f"Used      {model}")
    items = print_reading_lesson(lesson)
    try:
        selected = choose_lesson_items_cli(items)
    except KeyboardInterrupt:
        print("\n\nCancelled — Anki was not changed.")
        return 130
    if not selected:
        return 0

    try:
        _require_generation_keys(gemini=False, aws=True)
    except BackfillSafetyError as error:
        print(f"❌ {error}")
        return 1

    features = {
        "production_card": not (
            args.original_card or args.no_production_card
        ),
        "common_phrases": not (
            args.original_card or args.no_common_phrases
        ),
        "smart_grammar": not (
            args.original_card or args.no_smart_grammar
        ),
        "listening_card": (
            args.listening_card
            and not args.original_card
            and not args.no_listening_card
        ),
        "sentence_cloze": (
            args.sentence_cloze
            and not args.original_card
            and not args.no_sentence_cloze
        ),
    }
    _print_lesson_heading("Creating selected cards")
    print(f"Adding {len(selected)} item(s) to Anki…\n")
    added = 0
    for item in selected:
        target = str(
            item.get("card_target") or item.get("term") or ""
        ).strip()
        context = str(item.get("source_excerpt") or "").strip()
        if not target:
            continue
        try:
            if add_word_to_anki(
                target,
                args.language,
                translation_lang=args.translation,
                feature_options=features,
                usage_context=context,
                gemini_api_key=teacher_gemini_key,
            ):
                added += 1
        except KeyboardInterrupt:
            print(
                "\n\nStopped — no more cards will be created. "
                f"Completed before stopping: {added} of {len(selected)}."
            )
            return 130
        print("-" * 40)

    print(_terminal_style(
        f"\nDone — added {added} of {len(selected)} selected card(s).",
        "1",
        "32" if added == len(selected) else "33",
    ))
    return 0 if added == len(selected) else 1


def _print_practice_feedback(feedback):
    _print_lesson_heading("Focused feedback")
    overall_en = str(feedback.get("overall_en") or "").strip()
    overall_fa = str(feedback.get("overall_fa") or "").strip()
    if overall_en:
        _print_wrapped(overall_en, first="English  ", rest="         ")
    if overall_fa:
        _print_wrapped(overall_fa, first="Persian  ", rest="         ")
    strengths = [
        str(value).strip()
        for value in (feedback.get("strengths") or [])
        if str(value).strip()
    ]
    if strengths:
        print()
        for value in strengths[:2]:
            _print_wrapped(value, first="  ✓ ", rest="    ")

    print()
    for result in feedback.get("target_results") or []:
        word = str(result.get("word") or "").strip()
        correct = bool(result.get("correct"))
        symbol = "✓" if correct else "→"
        color = "32" if correct else "33"
        print(_terminal_style(f"{symbol} {word}", "1", color))
        feedback_en = str(result.get("feedback_en") or "").strip()
        feedback_fa = str(result.get("feedback_fa") or "").strip()
        if feedback_en:
            _print_wrapped(feedback_en, first="  ", rest="  ")
        if feedback_fa:
            _print_wrapped(feedback_fa, first="  ", rest="  ")


def _run_practice_cli(args):
    """Run one adaptive production task from already-studied recall cards."""
    print("\n" + _terminal_style("ANKI PRACTICE", "1", "36"))
    print(_terminal_style("─" * _terminal_text_width(), "36"))
    print("Mode      Real-life production · focused feedback · one AI call")
    print("Anki      Read-only unless you approve a repeated-error card")
    try:
        state = load_practice_state(BASE_DIR)
        candidates = discover_practice_candidates(
            invoke_anki,
            source_model_name=NOTE_TYPE,
            recall_model_name=OWNED_MODEL_NAME,
        )
        targets = select_practice_targets(candidates, state, count=3)
    except Exception as error:
        print(f"❌ {error}")
        return 1
    if not targets:
        print(
            "No studied production-recall cards are available yet. "
            "Review some production cards, then run `anki practice` again."
        )
        return 0

    task = build_practice_task(targets, state)
    print(f"Selected  {len(targets)} of {len(candidates)} studied words")
    print(f"Task      {task['title']}")
    _print_lesson_heading("Your task")
    _print_wrapped(str(task["prompt_en"]), first="English  ", rest="         ")
    _print_wrapped(str(task["prompt_fa"]), first="Persian  ", rest="         ")
    print("\nTargets   " + " · ".join(target["word"] for target in targets))

    if not sys.stdin.isatty():
        print("\nPreview only — no Gemini request, history update, or Anki change.")
        return 0

    try:
        response = input(
            "\nWrite 2–4 Italian sentences (q cancels)\nItalian › "
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nCancelled — nothing was changed.")
        return 130
    if response.casefold() in {"q", "quit", "cancel"}:
        print("Cancelled — nothing was changed.")
        return 0
    if not response:
        print("No response entered — nothing was changed.")
        return 0

    try:
        _require_generation_keys(gemini=False, aws=False, teach=True)
        practice_key = GEMINI_TEACH_API_KEY or GEMINI_API_KEY
        print("\nStatus    Checking meaning, form, grammar, and naturalness…")
        feedback = generate_practice_feedback(
            targets,
            task,
            response,
            practice_key,
        )
    except KeyboardInterrupt:
        print("\n\nCancelled — practice history and Anki were not changed.")
        return 130
    except (ValueError, BackfillSafetyError) as error:
        print(f"❌ {error}")
        return 1
    except Exception as error:
        print(f"❌ {_format_gemini_error(error)}")
        return 1
    if feedback.get("error"):
        print(f"❌ Gemini Error: {feedback['error']}")
        return 1

    print(f"Model     {feedback.get('_gemini_model') or 'unknown'}")
    _print_practice_feedback(feedback)

    if feedback.get("retry_needed"):
        retry_en = str(feedback.get("retry_instruction_en") or "").strip()
        retry_fa = str(feedback.get("retry_instruction_fa") or "").strip()
        _print_lesson_heading("Retry before the model answer")
        if retry_en:
            _print_wrapped(retry_en, first="English  ", rest="         ")
        if retry_fa:
            _print_wrapped(retry_fa, first="Persian  ", rest="         ")
        try:
            input("\nRewrite once in Italian › ")
        except (KeyboardInterrupt, EOFError):
            print("\nRetry skipped.")

    corrected = str(feedback.get("corrected_response_it") or "").strip()
    if corrected:
        _print_lesson_heading("Model correction")
        _print_wrapped(corrected, first="Italian  ", rest="         ")

    repeated = update_practice_state(state, targets, feedback)
    try:
        save_practice_state(BASE_DIR, state)
    except OSError as error:
        print(f"⚠️  Feedback was shown, but practice history was not saved: {error}")
        repeated = []

    if repeated:
        _print_lesson_heading("Repeated mistake")
        print(
            "The same error has now occurred twice for: "
            + ", ".join(entry["word"] for entry in repeated)
        )
        try:
            answer = input(
                "Create a small correction card for these errors? [y/N] "
            ).strip().casefold()
        except (KeyboardInterrupt, EOFError):
            answer = ""
        if answer in {"y", "yes"}:
            try:
                result = create_correction_cards(
                    invoke_anki,
                    repeated,
                    source_deck=DECK_NAME,
                )
                print(
                    f"✅ Added {result['added']} correction card(s)"
                    + (
                        f"; skipped {result['skipped']} existing/invalid item(s)."
                        if result["skipped"] else "."
                    )
                )
            except Exception as error:
                print(f"❌ Correction cards were not created: {error}")
                return 1
        else:
            print("No correction card was created.")
        mark_correction_offer(state, repeated)
        save_practice_state(BASE_DIR, state)

    print("\nPractice complete. The original cards and review history were unchanged.")
    return 0

def build_parser():
    parser = argparse.ArgumentParser(
        description="Add words to Anki or learn from copied Italian text.",
        epilog=(
            "Reading lesson: copy an article on macOS, then run `anki teach`. "
            "It will not add cards until you select them."
        ),
    )
    parser.add_argument(
        "words",
        nargs="*",
        help="Words to add, or the special commands `teach` and `practice`",
    )
    parser.add_argument("-f", "--file", help="File containing a list of words, one per line")
    parser.add_argument(
        "-c",
        "--context",
        help=(
            "Sentence or paragraph showing how one target word is used; "
            "the normal word-only command remains unchanged"
        ),
    )
    parser.add_argument(
        "-l",
        "--language",
        default=None,
        help="Language for new generation (default: Italian)",
    )
    parser.add_argument(
        "-t",
        "--translation",
        default=None,
        help=(
            "Translation language for new generation "
            "(default: Both (English + Persian))"
        ),
    )
    parser.add_argument("--no-production-card", action="store_true", help="Keep only the original recognition card")
    parser.add_argument("--no-common-phrases", action="store_true", help="Do not add common phrases")
    parser.add_argument("--no-smart-grammar", action="store_true", help="Do not add smart Italian grammar")
    parser.add_argument("--listening-card", action="store_true", help="Enable listening comprehension card (audio-only front)")
    parser.add_argument("--no-listening-card", action="store_true", help="Do not create a listening comprehension card")
    parser.add_argument("--sentence-cloze", action="store_true", help="Enable sentence cloze card (contextual gap-fill)")
    parser.add_argument("--no-sentence-cloze", action="store_true", help="Do not create a sentence cloze card")
    parser.add_argument("--original-card", action="store_true", help="Disable all optional learning features")

    migration = parser.add_mutually_exclusive_group()
    migration.add_argument(
        "--backfill-production",
        action="store_true",
        help=(
            "Preview isolated production-recall cards for existing notes; "
            "add --apply to create them"
        ),
    )
    migration.add_argument(
        "--resume-production-backfill",
        metavar="RUN_ID",
        help="Preview or resume an interrupted production backfill",
    )
    migration.add_argument(
        "--undo-production-backfill",
        metavar="RUN_ID",
        help=(
            "Preview deletion of recall notes from one migration run; "
            "add --apply to delete them"
        ),
    )
    migration.add_argument(
        "--upgrade-production-audio",
        action="store_true",
        help=(
            "Preview enabling a visible word-audio button on old "
            "production-recall cards; add --apply to update templates"
        ),
    )
    migration.add_argument(
        "--recall-sort-field",
        choices=("word", "source-id"),
        help=(
            "Preview changing the app-owned recall note type's browser "
            "sort field; add --apply to make the change"
        ),
    )
    migration.add_argument(
        "--install-recall-sort-helper",
        action="store_true",
        help=(
            "Preview installing the restricted Anki helper required to "
            "change the recall sort field from the CLI"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly allow the selected migration or rollback to mutate Anki",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit preview mode (migration commands already preview by default)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the typed confirmation when --apply is also present",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N eligible existing notes",
    )
    parser.add_argument(
        "--note-id",
        action="append",
        type=int,
        dest="note_ids",
        help="Restrict backfill to one source note ID (repeatable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "With rollback only, delete an owned recall note even if its "
            "generated content was edited"
        ),
    )
    return parser


def _require_generation_keys(*, gemini=True, aws=True, teach=False):
    missing = [
        name
        for name, value in (
            ("GEMINI_API_KEY", GEMINI_API_KEY if gemini else "unused"),
            (
                "GEMINI_TEACH_API_KEY or GEMINI_API_KEY",
                (GEMINI_TEACH_API_KEY or GEMINI_API_KEY)
                if teach else "unused",
            ),
            ("AWS_ACCESS_KEY", AWS_ACCESS_KEY if aws else "unused"),
            ("AWS_SECRET_KEY", AWS_SECRET_KEY if aws else "unused"),
        )
        if not value
    ]
    if missing:
        raise BackfillSafetyError(
            "Missing API keys in .env: " + ", ".join(missing)
        )


def _confirm_mutation(expected_word, message, assume_yes=False):
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise BackfillSafetyError(
            f"Interactive confirmation is unavailable. Review the preview, "
            f"then rerun with --apply --yes to confirm {expected_word}."
        )
    print(message)
    typed = input(f"Type {expected_word} to continue: ").strip()
    if typed != expected_word:
        raise BackfillSafetyError("Cancelled. Nothing was changed.")


def _print_backfill_preview(discovery, language, translation):
    print("\nProduction backfill preview (read-only)")
    print(f"  Source deck:              {DECK_NAME}")
    print(f"  Source note type:         {NOTE_TYPE}")
    print("  Recall note type:         AG Production Recall v1")
    print(f"  Recall destination deck: {PRODUCTION_RECALL_DECK}")
    print(f"  Language:                 {language}")
    print(f"  Translation:              {translation}")
    print(f"  Source notes found:        {discovery['source_count']}")
    print(f"  Eligible existing notes:   {discovery['eligible_total']}")
    print(f"  Selected for this run:     {discovery['selected_count']}")
    print(
        "  Already have recall card: "
        f"{len(discovery['already_same_note'])}"
    )
    print(
        "  Already safely backfilled: "
        f"{len(discovery['already_backfilled'])}"
    )
    print(f"  Skipped for safety:        {len(discovery['invalid'])}")
    if discovery["excluded_by_limit"]:
        print(
            "  Excluded by --limit:       "
            f"{discovery['excluded_by_limit']}"
        )
    if discovery["missing_requested"]:
        print(
            "  Requested IDs not in scope: "
            + ", ".join(map(str, discovery["missing_requested"]))
        )
    if discovery["candidates"]:
        samples = ", ".join(
            f"{item['word']} ({item['note']['noteId']})"
            for item in discovery["candidates"][:8]
        )
        print(f"  First selected notes:      {samples}")
    print(
        "\nPreview made no changes. Existing source notes and their review "
        "history are read-only in this migration."
    )


def _manifest_stage_counts(manifest):
    counts = {}
    for item in manifest.get("items") or []:
        stage = str(item.get("stage") or "unknown")
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def _resume_key_requirements(manifest):
    needs_gemini = False
    needs_aws = False
    for item in manifest.get("items") or []:
        stage = item.get("stage")
        if stage == "pending":
            needs_gemini = True
            needs_aws = True
        elif stage == "generated" and not audio_cache_is_valid(item):
            needs_aws = True
    return needs_gemini, needs_aws


def _print_manifest_issues(manifest, limit=8):
    issues = [
        item
        for item in manifest.get("items") or []
        if item.get("last_error")
        or item.get("stage") in {"conflict", "cleanup_required"}
    ]
    if not issues:
        return
    print("\nItems needing attention:")
    for item in issues[:limit]:
        print(
            f"  - {item.get('word')} "
            f"(note {item.get('source_note_id')}, "
            f"stage {item.get('stage')}): {item.get('last_error')}"
        )


def _print_migration_next_steps(manifest):
    run_id = manifest["run_id"]
    retryable = [
        item
        for item in manifest.get("items") or []
        if item.get("stage")
        in {"pending", "generated", "media_stored", "note_added"}
    ]
    terminal = [
        item
        for item in manifest.get("items") or []
        if item.get("stage") in {"conflict", "cleanup_required"}
    ]
    cleanup_required = any(
        item.get("stage") == "cleanup_required"
        for item in manifest.get("items") or []
    )
    if retryable and not cleanup_required:
        print(
            "Resume retryable items with:\n"
            f"  python3 cli.py --resume-production-backfill "
            f"{run_id} --apply"
        )
    if terminal:
        print(
            "Conflict/cleanup items are not retried automatically. Preview "
            "the run-specific cleanup with:\n"
            f"  python3 cli.py --undo-production-backfill {run_id}"
        )


def _run_backfill_cli(args):
    workspace = Path(BASE_DIR)
    if args.resume_production_backfill:
        path = resolve_manifest_path(
            workspace,
            args.resume_production_backfill,
        )
        manifest = load_manifest(path)
        counts = _manifest_stage_counts(manifest)
        print(f"\nBackfill run: {manifest['run_id']}")
        print(f"Manifest: {path}")
        print(f"Source deck: {manifest['source_deck']}")
        print(
            "Recall destination deck: "
            f"{manifest.get('destination_deck', manifest['source_deck'])}"
        )
        print(f"Source note type: {manifest['source_model_name']}")
        print(f"Recall note type: {manifest['owned_model_name']}")
        print(f"Saved language: {manifest['language']}")
        print(f"Saved translation: {manifest['translation']}")
        print(f"Run state: {manifest.get('state')}")
        print(
            "Stages: "
            + ", ".join(
                f"{name}={count}"
                for name, count in sorted(counts.items())
            )
        )
        if not args.apply:
            _print_manifest_issues(manifest)
            print(
                "Preview only. Add --apply to resume pending or failed items."
            )
            return 0
        if manifest.get("state") == "completed":
            print("This run is already complete; nothing was changed.")
            return 0
        if manifest.get("state") in {
            "rolling_back",
            "rollback_partial",
            "rolled_back",
        }:
            raise BackfillSafetyError(
                "This run has entered rollback and cannot be resumed."
            )
        if any(
            item.get("stage") == "cleanup_required"
            for item in manifest.get("items") or []
        ):
            _print_manifest_issues(manifest)
            _print_migration_next_steps(manifest)
            return 1
        needs_gemini, needs_aws = _resume_key_requirements(manifest)
        if not needs_gemini and not needs_aws:
            summary = manifest.get("summary") or {}
            if int(summary.get("conflicts") or 0):
                _print_manifest_issues(manifest)
                return 1
        _require_generation_keys(
            gemini=needs_gemini,
            aws=needs_aws,
        )
        _confirm_mutation(
            "RESUME",
            "This resumes only the journaled, unfinished recall notes. "
            "Source notes remain read-only.",
            args.yes,
        )
        summary = apply_manifest(
            invoke_anki,
            path,
            gemini_api_key=GEMINI_API_KEY,
            aws_access_key=AWS_ACCESS_KEY,
            aws_secret_key=AWS_SECRET_KEY,
            generate_content=generate_content,
            create_polly_client=create_polly_client,
            generate_audio=generate_audio,
            language_configs=LANGUAGE_CONFIGS,
        )
        print(f"\nBackfill result: {summary}")
        print(f"Rollback ID: {manifest['run_id']}")
        refreshed = load_manifest(path)
        _print_manifest_issues(refreshed)
        if summary["remaining"] or summary["conflicts"]:
            _print_migration_next_steps(refreshed)
            return 1
        return 0

    discovery = discover_candidates(
        invoke_anki,
        DECK_NAME,
        NOTE_TYPE,
        limit=args.limit,
        requested_note_ids=args.note_ids,
    )
    _print_backfill_preview(
        discovery,
        args.language,
        args.translation,
    )
    if not args.apply:
        print(
            "\nTo test a small reversible batch:\n"
            "  python3 cli.py --backfill-production --limit 10 --apply"
        )
        return 0
    if discovery["missing_requested"]:
        raise BackfillSafetyError(
            "One or more requested --note-id values are outside the "
            "configured deck/note type. Apply was blocked."
        )
    if not discovery["selected_count"]:
        print("Nothing eligible was selected; nothing was changed.")
        return 0
    if args.language not in LANGUAGE_CONFIGS:
        raise BackfillSafetyError(
            f'Unsupported language "{args.language}". Nothing was changed.'
        )

    _require_generation_keys()
    _confirm_mutation(
        "BACKFILL",
        (
            f"\nThis will create {discovery['selected_count']} new recall "
            "notes in a separate app-owned note type. It will first export "
            "a scheduled Anki backup. It will not update any source field, "
            "template, card ID, or review record."
        ),
        args.yes,
    )
    path = prepare_manifest(
        invoke_anki,
        workspace,
        DECK_NAME,
        NOTE_TYPE,
        args.language,
        args.translation,
        discovery,
        destination_deck=PRODUCTION_RECALL_DECK,
    )
    manifest = load_manifest(path)
    print(f"Scheduled backup: {manifest['backup']['path']}")
    print(f"Migration manifest: {path}")
    summary = apply_manifest(
        invoke_anki,
        path,
        gemini_api_key=GEMINI_API_KEY,
        aws_access_key=AWS_ACCESS_KEY,
        aws_secret_key=AWS_SECRET_KEY,
        generate_content=generate_content,
        create_polly_client=create_polly_client,
        generate_audio=generate_audio,
        language_configs=LANGUAGE_CONFIGS,
    )
    print(f"\nBackfill result: {summary}")
    print(f"Rollback ID: {manifest['run_id']}")
    print(
        "The original cards were not edited. Keep the rollback ID if you "
        "want to remove only this run's new recall notes."
    )
    refreshed = load_manifest(path)
    _print_manifest_issues(refreshed)
    if summary["remaining"] or summary["conflicts"]:
        _print_migration_next_steps(refreshed)
        return 1
    return 0


def _run_rollback_cli(args):
    workspace = Path(BASE_DIR)
    path = resolve_manifest_path(
        workspace,
        args.undo_production_backfill,
    )
    preview = inspect_rollback(
        invoke_anki,
        path,
        force=args.force,
    )
    print("\nProduction backfill rollback preview (read-only)")
    manifest = load_manifest(path)
    print(f"  Migration run:         {manifest['run_id']}")
    print(f"  Source deck:           {manifest['source_deck']}")
    print(f"  Source note type:      {manifest['source_model_name']}")
    print(f"  Recall note type:      {manifest['owned_model_name']}")
    print(f"  Recall notes to delete: {len(preview['deletable'])}")
    print(f"  Already absent:         {len(preview['already_missing'])}")
    print(f"  Ownership/edit conflicts: {len(preview['conflicts'])}")
    print(
        "  App-owned audio files left for Anki Check Media: "
        f"{len(set(preview['media_files_left']))}"
    )
    if preview["target_decks"]:
        print(
            "  Decks backed up before deletion: "
            + ", ".join(preview["target_decks"])
        )
    if args.force:
        print(
            "  ⚠️ FORCE ENABLED: edited app-owned recall notes may be deleted."
        )
    if preview["conflicts"]:
        for conflict in preview["conflicts"][:8]:
            print(
                f"    - {conflict['note_id']}: {conflict['reason']}"
            )
    print(
        "\nOriginal notes, original cards, and their review history are not "
        "rollback targets."
    )
    if not args.apply:
        print(
            "Preview made no changes. Add --apply after reviewing this list."
        )
        return 0
    if not preview["deletable"] and not preview["conflicts"]:
        result = apply_rollback(
            invoke_anki,
            workspace,
            path,
            force=args.force,
        )
        print(
            "No recall notes existed. The migration journal is now sealed "
            "as rolled back, so it cannot later be resumed."
        )
        print(f"Rollback result: {result}")
        return 0
    if preview["conflicts"]:
        raise BackfillSafetyError(
            "Resolve the conflicts, or use --force only if deleting edited "
            "app-owned recall notes is intentional."
        )
    _confirm_mutation(
        "ROLLBACK",
        (
            "This deletes only the app-owned recall notes from this run and "
            "their recall-card history. A new scheduled backup is exported "
            "first. Original-card history remains untouched."
        ),
        args.yes,
    )
    result = apply_rollback(
        invoke_anki,
        workspace,
        path,
        force=args.force,
    )
    print(f"\nRollback result: {result}")
    print(
        "Unique production audio was left in Anki media for safety; Anki's "
        "Tools > Check Media can remove it later."
    )
    return 0 if not result["conflicts"] else 1


def _production_audio_template_targets():
    """Known template versions that can be upgraded without touching notes."""
    return (
        {
            "model_name": NOTE_TYPE,
            "template_name": PRODUCTION_TEMPLATE_NAME,
            "front": PRODUCTION_TEMPLATE_FRONT,
            "legacy_back": PRODUCTION_TEMPLATE_BACK_LEGACY,
            "current_back": PRODUCTION_TEMPLATE_BACK,
            "production_field": PRODUCTION_BACK_FIELD,
        },
        {
            "model_name": OWNED_MODEL_NAME,
            "template_name": OWNED_TEMPLATE_NAME,
            "front": OWNED_TEMPLATE_FRONT,
            "legacy_back": OWNED_TEMPLATE_BACK_LEGACY,
            "current_back": OWNED_TEMPLATE_BACK,
            "production_field": "ProductionBack",
        },
    )


def _inspect_production_audio_upgrade():
    """Classify the two app-owned recall templates without mutating Anki."""
    model_names = set((invoke_anki("modelNamesAndIds") or {}).keys())
    result = []
    for target in _production_audio_template_targets():
        model_name = target["model_name"]
        item = dict(target)
        item["note_count"] = 0
        if model_name not in model_names:
            item["status"] = "model_missing"
            result.append(item)
            continue

        templates = invoke_anki(
            "modelTemplates",
            {"modelName": model_name},
        ) or {}
        template = templates.get(target["template_name"])
        if template is None:
            item["status"] = "template_missing"
        else:
            front = str(template.get("Front") or "")
            back = str(template.get("Back") or "")
            if (
                front == target["front"]
                and back == target["current_back"]
            ):
                item["status"] = "current"
            elif (
                front == target["front"]
                and back == target["legacy_back"]
            ):
                item["status"] = "upgradeable"
            else:
                item["status"] = "conflict"

        escaped_model = _anki_search_literal(model_name)
        note_ids = invoke_anki(
            "findNotes",
            {"query": f'note:"{escaped_model}"'},
        ) or []
        for index in range(0, len(note_ids), 500):
            notes = invoke_anki(
                "notesInfo",
                {"notes": note_ids[index:index + 500]},
            ) or []
            item["note_count"] += sum(
                bool(str(
                    (
                        (note.get("fields") or {})
                        .get(item["production_field"], {})
                        .get("value")
                    ) or ""
                ).strip())
                for note in notes
            )
        result.append(item)
    return result


def _apply_production_audio_upgrade(preview):
    conflicts = [item for item in preview if item["status"] == "conflict"]
    if conflicts:
        names = ", ".join(item["model_name"] for item in conflicts)
        raise BackfillSafetyError(
            "The production template was manually changed for: "
            f"{names}. Nothing was updated."
        )

    upgraded = []
    for item in preview:
        if item["status"] != "upgradeable":
            continue
        invoke_anki(
            "updateModelTemplates",
            {
                "model": {
                    "name": item["model_name"],
                    "templates": {
                        item["template_name"]: {
                            "Front": item["front"],
                            "Back": item["current_back"],
                        },
                    },
                },
            },
        )
        templates = invoke_anki(
            "modelTemplates",
            {"modelName": item["model_name"]},
        ) or {}
        verified = templates.get(item["template_name"]) or {}
        if (
            str(verified.get("Front") or "") != item["front"]
            or str(verified.get("Back") or "") != item["current_back"]
        ):
            raise BackfillSafetyError(
                "Anki did not save the word-audio template for "
                f"{item['model_name']}."
            )
        upgraded.append(item)
    return upgraded


def _run_production_audio_upgrade_cli(args):
    preview = _inspect_production_audio_upgrade()
    print("\nProduction recall word-audio upgrade")
    print("This changes templates only; notes and review history stay intact.")
    for item in preview:
        status = item["status"]
        if status == "upgradeable":
            detail = f"ready to enable on {item['note_count']} note(s)"
        elif status == "current":
            detail = f"already enabled for {item['note_count']} note(s)"
        elif status == "model_missing":
            detail = "note type does not exist"
        elif status == "template_missing":
            detail = "production template does not exist"
        else:
            detail = "template was manually changed; stopped for safety"
        print(f"  - {item['model_name']}: {detail}")

    if any(item["status"] == "conflict" for item in preview):
        raise BackfillSafetyError(
            "A production template is not an exact app-owned version. "
            "Nothing was changed."
        )
    upgradeable = [
        item for item in preview if item["status"] == "upgradeable"
    ]
    if not args.apply:
        if upgradeable:
            print(
                "\nPreview made no changes. Apply it with:\n"
                "  anki --upgrade-production-audio --apply"
            )
        return 0
    if not upgradeable:
        print("\nNothing changed; old production cards are already enabled.")
        return 0

    _confirm_mutation(
        "AUDIO",
        (
            "This updates only the app-owned production-card templates. "
            "It does not rewrite notes, scheduling, or review history."
        ),
        args.yes,
    )
    upgraded = _apply_production_audio_upgrade(preview)
    note_count = sum(item["note_count"] for item in upgraded)
    print(
        f"\n✅ Enabled the word-audio button for {note_count} old "
        "production note(s)."
    )
    return 0


def _validate_operation_args(parser, args):
    migration_selected = bool(
        args.backfill_production
        or args.resume_production_backfill
        or args.undo_production_backfill
        or args.recall_sort_field
        or args.install_recall_sort_helper
        or args.upgrade_production_audio
    )
    teacher_selected = bool(
        args.words
        and str(args.words[0]).strip().casefold() == "teach"
    )
    practice_selected = bool(
        args.words
        and str(args.words[0]).strip().casefold() == "practice"
    )
    if teacher_selected and len(args.words) != 1:
        parser.error(
            "`anki teach` reads the article from your clipboard; "
            "do not put text or words after `teach`."
        )
    if teacher_selected and (args.file or args.context):
        parser.error(
            "`anki teach` reads directly from the clipboard and cannot use "
            "--file or --context."
        )
    if practice_selected and len(args.words) != 1:
        parser.error("`anki practice` does not accept words after `practice`.")
    if practice_selected and (args.file or args.context):
        parser.error(
            "`anki practice` selects studied words from Anki and cannot use "
            "--file or --context."
        )
    if args.apply and not migration_selected:
        parser.error("--apply is only valid with a migration command.")
    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply cannot be used together.")
    if args.dry_run and not migration_selected:
        parser.error("--dry-run is only valid with a migration command.")
    if args.yes and not args.apply:
        parser.error("--yes requires --apply.")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1.")
    if args.note_ids and any(note_id < 1 for note_id in args.note_ids):
        parser.error("--note-id values must be positive.")
    if migration_selected and (args.words or args.file):
        parser.error(
            "Words/files cannot be combined with a migration command."
        )
    if args.context and migration_selected:
        parser.error("--context cannot be combined with a migration command.")
    if args.context and (args.file or len(args.words) != 1):
        parser.error("--context requires exactly one target word and no --file.")
    if (
        args.undo_production_backfill
        and (args.limit is not None or args.note_ids)
    ):
        parser.error("--limit/--note-id are not valid with rollback.")
    if args.resume_production_backfill and (
        args.limit is not None or args.note_ids
    ):
        parser.error("--limit/--note-id are fixed by the saved manifest.")
    if args.force and not args.undo_production_backfill:
        parser.error("--force is only valid with rollback.")
    if (
        args.resume_production_backfill
        or args.undo_production_backfill
    ) and (args.language is not None or args.translation is not None):
        parser.error(
            "--language/--translation cannot override a saved migration."
        )
    if not args.backfill_production and (
        args.limit is not None or args.note_ids
    ):
        parser.error(
            "--limit/--note-id are only valid with --backfill-production."
        )
    if migration_selected and (
        args.original_card
        or args.no_production_card
        or args.no_common_phrases
        or args.no_smart_grammar
    ):
        parser.error(
            "Normal-card learning flags cannot be combined with a "
            "migration command."
        )
    return migration_selected


def _recall_sort_helper_paths():
    source = (
        Path(BASE_DIR)
        / "anki_addons"
        / "anki_generator_cli_bridge"
    )
    media_dir = Path(str(invoke_anki("getMediaDirPath") or "")).resolve()
    if (
        not media_dir.is_absolute()
        or media_dir.name != "collection.media"
        or len(media_dir.parents) < 2
    ):
        raise BackfillSafetyError(
            "Anki returned an unexpected media directory; helper "
            "installation was blocked."
        )
    target = (
        media_dir.parents[1]
        / "addons21"
        / "anki_generator_cli_bridge"
    )
    return source, target


def _run_install_recall_sort_helper_cli(args):
    source, target = _recall_sort_helper_paths()
    required_files = ("__init__.py", "manifest.json")
    if not all((source / name).is_file() for name in required_files):
        raise BackfillSafetyError(
            "The bundled recall sort helper is incomplete."
        )

    print("\nRestricted recall sort helper preview")
    print(f"  Install location: {target}")
    print("  Allowed note type: AG Production Recall v1")
    print("  Allowed fields: Word, AG_SourceNoteID")
    print(
        "\nThe helper cannot edit card content, scheduling, review history, "
        "other note types, or other fields."
    )
    if not args.apply:
        print(
            "\nPreview made no changes. Install it with:\n"
            "  python3 cli.py --install-recall-sort-helper --apply"
        )
        return 0

    _confirm_mutation(
        "INSTALL",
        "This will install the restricted helper into Anki's add-ons folder.",
        args.yes,
    )
    if target.is_symlink():
        raise BackfillSafetyError(
            "The helper target is a symbolic link; installation was blocked."
        )
    existing_code = target / "__init__.py"
    if (
        existing_code.exists()
        and existing_code.read_bytes()
        != (source / "__init__.py").read_bytes()
    ):
        raise BackfillSafetyError(
            "A different add-on already uses the helper folder name. "
            "Nothing was overwritten."
        )

    target.mkdir(parents=True, exist_ok=True)
    for filename in required_files:
        shutil.copy2(source / filename, target / filename)
    for filename in required_files:
        if (target / filename).read_bytes() != (source / filename).read_bytes():
            raise BackfillSafetyError(
                "The helper installation could not be verified."
            )

    print("\n✅ Restricted recall sort helper installed and verified.")
    print(
        "Restart Anki once, then run:\n"
        "  python3 cli.py --recall-sort-field word --apply"
    )
    return 0


def _run_recall_sort_field_cli(args):
    field_name = (
        "Word"
        if args.recall_sort_field == "word"
        else "AG_SourceNoteID"
    )
    label = (
        "the Italian word (for example, leggere)"
        if field_name == "Word"
        else "the source note ID"
    )
    current = inspect_owned_model_sort_field(invoke_anki)
    print("\nRecall browser sort-field preview")
    print("  Note type: AG Production Recall v1")
    print(f"  Current sort field: {current['sort_field']}")
    print(f"  Requested sort field: {field_name}")
    print(f"  New first column: {label}")
    print(
        "\nThis changes only the sort-field setting of the separate "
        "app-owned recall note type. Original cards, scheduling, templates, and "
        "review history are not changed."
    )
    if not args.apply:
        print(
            "\nPreview made no changes. Apply it with:\n"
            f"  python3 cli.py --recall-sort-field "
            f"{args.recall_sort_field} --apply"
        )
        return 0

    _confirm_mutation(
        "SORT",
        "This will change the recall note type's browser sort field.",
        args.yes,
    )
    result = set_owned_model_sort_field(invoke_anki, field_name)
    if result["changed"]:
        print(
            f"\n✅ Recall cards now show {label} in Anki's Sort Field column."
        )
    else:
        print(f"\nNothing changed; {label} is already the Sort Field.")
    opposite = "source-id" if args.recall_sort_field == "word" else "word"
    print(
        "To reverse this later:\n"
        f"  python3 cli.py --recall-sort-field {opposite} --apply"
    )
    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()
    migration_selected = _validate_operation_args(parser, args)
    if not (
        args.resume_production_backfill
        or args.undo_production_backfill
    ):
        args.language = args.language or "Italian"
        args.translation = (
            args.translation or "Both (English + Persian)"
        )

    try:
        if args.backfill_production or args.resume_production_backfill:
            return _run_backfill_cli(args)
        if args.undo_production_backfill:
            return _run_rollback_cli(args)
        if args.upgrade_production_audio:
            return _run_production_audio_upgrade_cli(args)
        if args.install_recall_sort_helper:
            return _run_install_recall_sort_helper_cli(args)
        if args.recall_sort_field:
            return _run_recall_sort_field_cli(args)
    except (BackfillSafetyError, FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    except Exception as error:
        print(f"❌ Migration failed safely: {error}")
        return 1

    if migration_selected:
        return 0

    if (
        len(args.words) == 1
        and str(args.words[0]).strip().casefold() == "practice"
    ):
        return _run_practice_cli(args)

    if (
        len(args.words) == 1
        and str(args.words[0]).strip().casefold() == "teach"
    ):
        return _run_teacher_cli(args)

    words_to_add = list(args.words)

    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                file_words = [line.strip() for line in f if line.strip()]
                words_to_add.extend(file_words)
        except Exception as e:
            print(f"Error reading file {args.file}: {e}")
            return 1

    if not words_to_add:
        print("No words provided. Use arguments or -f to provide a word list.")
        parser.print_help()
        return 1

    try:
        _require_generation_keys()
    except BackfillSafetyError as error:
        print(f"❌ {error}")
        return 1

    print(f"Found {len(words_to_add)} words to process. Starting...\n")
    
    success_count = 0
    features = {
        "production_card": not (
            args.original_card or args.no_production_card
        ),
        "common_phrases": not (
            args.original_card or args.no_common_phrases
        ),
        "smart_grammar": not (
            args.original_card or args.no_smart_grammar
        ),
        "listening_card": (
            args.listening_card
            and not args.original_card
            and not args.no_listening_card
        ),
        "sentence_cloze": (
            args.sentence_cloze
            and not args.original_card
            and not args.no_sentence_cloze
        ),
    }
    for word in words_to_add:
        try:
            success = add_word_to_anki(
                word,
                args.language,
                translation_lang=args.translation,
                feature_options=features,
                usage_context=args.context,
            )
        except KeyboardInterrupt:
            print(
                "\n\nCancelled safely — no more cards will be created. "
                f"Completed before stopping: {success_count} "
                f"of {len(words_to_add)}."
            )
            return 130
        if success:
            success_count += 1
        print("-" * 40)

    print(f"\n🎉 Finished processing. Successfully added {success_count} out of {len(words_to_add)} words.")
    return 0 if success_count == len(words_to_add) else 1

if __name__ == "__main__":
    sys.exit(main())
