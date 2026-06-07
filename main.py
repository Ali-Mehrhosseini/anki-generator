"""
add_word.py — Add an Italian word to Anki with AI-generated content + Polly audio.

Usage:
    python add_word.py gatto
    python add_word.py gatto cane libro      # batch mode

Pipeline:
    word -> Gemini (content) -> Polly (audio) -> AnkiConnect (save card)
"""

import os
import sys
import json
import base64
import requests
import boto3
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pathlib import Path

load_dotenv()

PROMPT_FILE = Path(__file__).parent / "prompt.md"
SYSTEM_INSTRUCTION = PROMPT_FILE.read_text(encoding="utf-8")

# ============================================================
# 1. CONFIG — fill these in
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")

DECK_NAME      = os.getenv("DECK_NAME", "Italian")
NOTE_TYPE      = os.getenv("NOTE_TYPE", "Italian Vocab")
POLLY_VOICE    = os.getenv("POLLY_VOICE", "Beatrice")
ANKICONNECT    = os.getenv("ANKICONNECT", "http://localhost:8765")

# ============================================================
# 2. CLIENTS — created once, reused for every word in batch mode
# ============================================================
gemini = genai.Client(api_key=GEMINI_API_KEY)

polly = boto3.client(
    "polly",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# ============================================================
# 3. AnkiConnect helper
# ============================================================
def anki(action: str, **params):
    """Send a JSON request to the local AnkiConnect server."""
    try:
        res = requests.post(
            ANKICONNECT,
            json={"action": action, "version": 6, "params": params},
            timeout=10,
        ).json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to Anki. Please ensure Anki is open and AnkiConnect is installed/running.")

    if res.get("error"):
        raise RuntimeError(f"AnkiConnect error on '{action}': {res['error']}")
    return res["result"]

def check_anki_status() -> bool:
    try:
        requests.post(ANKICONNECT, json={"action": "version", "version": 6}, timeout=2)
        return True
    except requests.exceptions.ConnectionError:
        return False

# ============================================================
# 4. Step 1: ask Gemini for structured content
# ============================================================

# ============================================================
# 5. Step 2: ask Polly to record the example sentence
# ============================================================
def generate_content(word: str) -> dict:
    response = gemini.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=word,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
          response_schema={
    "type": "object",
    "properties": {
        "word":              {"type": "string"},
        "front_html":        {"type": "string"},
        "back_html":         {"type": "string"},
        "tts_word":          {"type": "string"},
        "tts_example":       {"type": "string"},
        "conjugation_field": {"type": "string"},
        "tts_io":            {"type": "string"},
        "tts_tu":            {"type": "string"},
        "tts_lui":           {"type": "string"},
        "tts_noi":           {"type": "string"},
        "tts_voi":           {"type": "string"},
        "tts_loro":          {"type": "string"},
    },
    "required": [
        "word", "front_html", "back_html",
        "tts_word", "tts_example", "conjugation_field",
        "tts_io", "tts_tu", "tts_lui",
        "tts_noi", "tts_voi", "tts_loro",
    ],
},
        ),
    )
    return json.loads(response.text)
#======================
def generate_audio(text: str) -> bytes:
    speech = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=POLLY_VOICE,
        Engine="generative",        
        LanguageCode="it-IT",
    )
    return speech["AudioStream"].read()

# ============================================================
# 6. Step 3: save audio + add the note in Anki
# ============================================================
PRONOUNS = ["io", "tu", "lui", "noi", "voi", "loro"]

def add_to_anki(data: dict, audios: dict[str, bytes]) -> int:
    """audios is a dict mapping suffix → mp3 bytes,
       e.g. {'': bytes, '_example': bytes, '_io': bytes, ...}"""
    word = data["word"]

    # store every audio file with its matching filenamef
    for suffix, mp3_bytes in audios.items():
        filename = f"{word}{suffix}.mp3"
        anki("storeMediaFile",filename=filename,data=base64.b64encode(mp3_bytes).decode())
    return anki("addNote", note={
        "deckName":  DECK_NAME,
        "modelName": NOTE_TYPE,
        "fields": {
            "Word":        word,
            "Front":       data["front_html"],
            "Back":        data["back_html"],
            "WordAudio":   f"[sound:{word}.mp3]",
            "Audio":       f"[sound:{word}_example.mp3]",
            "Conjugation": data["conjugation_field"],
        },
        "tags": ["auto", "italian"],
        "options": {"allowDuplicate": False},
    
    })

# ============================================================
# 7. Orchestrator: one word, top to bottom
# ============================================================
def process_word(user_input: str) -> dict:
    user_input = user_input.strip()
    print(f"→ {user_input}")
    try:
        data = generate_content(user_input)
        is_verb = bool(data["conjugation_field"])
        print(f"   Gemini: word={data['word']}, verb={'yes' if is_verb else 'no'}")

        # always need word audio + example audio
        audios = {
            "":         generate_audio(data["tts_word"]),
            "_example": generate_audio(data["tts_example"]),
        }

        # verbs need six more — one per pronoun
        if is_verb:
            for p in PRONOUNS:
                audios[f"_{p}"] = generate_audio(data[f"tts_{p}"])

        total = sum(len(b) for b in audios.values())
        print(f"   Polly:  {len(audios)} clips, {total:,} bytes")

        note_id = add_to_anki(data, audios)
        print(f"   ✅ Anki note {note_id}")
        audios_b64 = {k: base64.b64encode(v).decode() for k, v in audios.items()}
        return {"success": True, "note_id": note_id, "data": data, "audios": audios_b64}
    except Exception as e:
        print(f"   ❌ {e}")
        return {"success": False, "error": str(e)}
# ============================================================
# 8. CLI entry point
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_word.py <word> [<word> ...]")
        sys.exit(1)
    for w in sys.argv[1:]:
        process_word(w)
