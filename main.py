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
SYSTEM_INSTRUCTION_TEMPLATE = PROMPT_FILE.read_text(encoding="utf-8")

# ============================================================
# 1. CONFIG — fill these in
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")

DECK_NAME      = os.getenv("DECK_NAME", "Italian")
NOTE_TYPE      = os.getenv("NOTE_TYPE", "Italian Vocab")
ANKICONNECT    = os.getenv("ANKICONNECT", "http://localhost:8765")

LANGUAGE_CONFIGS = {
    "Italian": {"voice": "Beatrice", "code": "it-IT", "engine": "generative"},
    "Spanish": {"voice": "Lucia", "code": "es-ES", "engine": "generative"},
    "French": {"voice": "Ambre", "code": "fr-FR", "engine": "generative"},
    "German": {"voice": "Lennart", "code": "de-DE", "engine": "generative"},
    "Japanese": {"voice": "Mizuki", "code": "ja-JP", "engine": "neural"},
}

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

def get_anki_info() -> dict:
    try:
        decks = anki("deckNames")
        models = anki("modelNames")
        return {"success": True, "decks": decks, "models": models}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_duplicate(word: str, deck_name: str) -> bool:
    try:
        decks = anki("deckNames")
        if deck_name not in decks:
            return False
        res = anki("findNotes", query=f'"deck:{deck_name}" "Word:{word}"')
        return len(res) > 0
    except Exception:
        return False

# ============================================================
# 4. Step 1: ask Gemini for structured content
# ============================================================

# ============================================================
# 5. Step 2: ask Polly to record the example sentence
# ============================================================
def generate_content(word: str, language: str, custom_prompt: str = None, translation_lang: str = "Both (English + Persian)") -> dict:
    base_prompt = custom_prompt if custom_prompt else SYSTEM_INSTRUCTION_TEMPLATE
    system_instruction = base_prompt.replace("{LANGUAGE}", language)

    # Inject translation preferences
    if translation_lang == "English":
        meaning_html = "<div style=\"font-size:24px;font-weight:600;margin-bottom:4px;\">[EN_MEANING]</div>"
        example_html = "<div style=\"opacity:0.8;font-size:17px;margin-top:4px;\">[EN_EXAMPLE_1]</div>"
        trans_instruction = "## 🌐 Meaning line\\nThe first line of the Back is the English meaning."
    elif translation_lang == "Persian":
        meaning_html = "<div style=\"font-size:24px;font-weight:600;margin-bottom:4px;\"><span style=\"font-family:'Vazirmatn','Vazir',Tahoma,'Iranian Sans',sans-serif;font-weight:600;\">[FA_MEANING]</span></div>"
        example_html = "<div style=\"opacity:0.8;font-size:17px;margin-top:4px;font-family:'Vazirmatn','Vazir',Tahoma,'Iranian Sans',sans-serif;\">[FA_EXAMPLE_1]</div>"
        trans_instruction = "## 🌐 Meaning line\\nThe first line of the Back is the Persian meaning. Persian must be **natural Persian**, not transliteration.\\nThe example sentence translation ([FA_EXAMPLE_1]) must also be in Persian."
    else: # Both
        meaning_html = "<div style=\"font-size:24px;font-weight:600;margin-bottom:4px;\">[EN_MEANING] <span style=\"font-family:'Vazirmatn','Vazir',Tahoma,'Iranian Sans',sans-serif;font-weight:500;opacity:0.7;font-size:20px;\">([FA_MEANING])</span></div>"
        example_html = "<div style=\"opacity:0.8;font-size:17px;margin-top:4px;\">[EN_EXAMPLE_1]</div>"
        trans_instruction = "## 🌐 Bilingual meaning line (English + Persian)\\nThe first line of the Back is the English meaning followed by the Persian meaning in parentheses. Persian must be **natural Persian**, not transliteration. Keep parentheses Latin `(` and `)`."

    system_instruction = system_instruction.replace("{MEANING_HTML}", meaning_html)
    system_instruction = system_instruction.replace("{EXAMPLE_HTML}", example_html)
    system_instruction = system_instruction.replace("{TRANSLATION_INSTRUCTION}", trans_instruction)

    response = gemini.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=word,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
          response_schema={
    "type": "object",
    "properties": {
        "error":             {"type": "string"},
        "word":              {"type": "string"},
        "front_html":        {"type": "string"},
        "back_html":         {"type": "string"},
        "tts_word":          {"type": "string"},
        "tts_example":       {"type": "string"},
        "conjugation_field": {"type": "string"},
        "tts_verb_1":        {"type": "string"},
        "tts_verb_2":        {"type": "string"},
        "tts_verb_3":        {"type": "string"},
        "tts_verb_4":        {"type": "string"},
        "tts_verb_5":        {"type": "string"},
        "tts_verb_6":        {"type": "string"},
    },
    "required": [
        "error", "word", "front_html", "back_html",
        "tts_word", "tts_example", "conjugation_field",
        "tts_verb_1", "tts_verb_2", "tts_verb_3",
        "tts_verb_4", "tts_verb_5", "tts_verb_6",
    ],
},
        ),
    )
    return json.loads(response.text)
#======================
def generate_audio(text: str, voice: str, lang_code: str, engine: str = "neural") -> bytes:
    speech = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice,
        Engine=engine,        
        LanguageCode=lang_code,
    )
    return speech["AudioStream"].read()

# ============================================================
# 6. Step 3: save audio + add the note in Anki
# ============================================================
PRONOUNS = ["io", "tu", "lui", "noi", "voi", "loro"]

def add_to_anki(data: dict, audios: dict[str, bytes], deck_name: str = None, model_name: str = None) -> int:
    """audios is a dict mapping suffix → mp3 bytes,
       e.g. {'': bytes, '_example': bytes, '_io': bytes, ...}"""
    word = data["word"]
    target_deck = deck_name or DECK_NAME
    target_model = model_name or NOTE_TYPE

    # Auto-create deck if it doesn't exist
    existing_decks = anki("deckNames")
    if target_deck not in existing_decks:
        anki("createDeck", deck=target_deck)

    # store every audio file with its matching filenamef
    for suffix, mp3_bytes in audios.items():
        filename = f"{word}{suffix}.mp3"
        anki("storeMediaFile",filename=filename,data=base64.b64encode(mp3_bytes).decode())
    return anki("addNote", note={
        "deckName":  target_deck,
        "modelName": target_model,
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
def process_word(user_input: str, language: str, target_deck: str, target_model: str, custom_prompt: str = None, translation_lang: str = "Both (English + Persian)") -> dict:
    user_input = user_input.strip()
    print(f"→ {user_input} ({language})")
    try:
        # 1. Ask Gemini to generate the content based on the prompt
        data = generate_content(user_input, language, custom_prompt=custom_prompt, translation_lang=translation_lang)
        
        # 2. Check if Gemini rejected the word (e.g. wrong language)
        if data.get("error"):
            print(f"   ❌ Gemini error: {data['error']}")
            return {"success": False, "error": data["error"]}
        
        config = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["Italian"])
        voice = config["voice"]
        lang_code = config["code"]
        engine = config.get("engine", "neural")

        is_verb = bool(data["conjugation_field"])
        print(f"   Gemini: word={data['word']}, verb={'yes' if is_verb else 'no'}")

        # always need word audio + example audio
        audios = {
            "":         generate_audio(data["tts_word"], voice, lang_code, engine),
            "_example": generate_audio(data["tts_example"], voice, lang_code, engine),
        }

        # verbs need six more
        if is_verb:
            for i in range(1, 7):
                audios[f"_{i}"] = generate_audio(data[f"tts_verb_{i}"], voice, lang_code, engine)

        total = sum(len(b) for b in audios.values())
        print(f"   Polly:  {len(audios)} clips, {total:,} bytes")

        note_id = add_to_anki(data, audios, target_deck, target_model)
        print(f"   ✅ Anki note {note_id}")
        audios_b64 = {k: base64.b64encode(v).decode() for k, v in audios.items()}
        return {"success": True, "note_id": note_id, "data": data, "audios": audios_b64}
    except Exception as e:
        error_msg = str(e)
        if "does not support the selected engine: generative" in error_msg:
            error_msg = f"AWS Polly Error: The voice '{voice}' does not support the 'generative' AI engine. Please update main.py to use 'neural' for {language}."
        print(f"   ❌ {error_msg}")
        return {"success": False, "error": error_msg}
# ============================================================
# 8. CLI entry point
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_word.py <word> [<word> ...]")
        sys.exit(1)
    for w in sys.argv[1:]:
        process_word(w)
