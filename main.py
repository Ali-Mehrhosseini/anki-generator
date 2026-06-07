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
import boto3
from google import genai
from google.genai import types
from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "prompt.md"
SYSTEM_INSTRUCTION_TEMPLATE = PROMPT_FILE.read_text(encoding="utf-8")

AWS_REGION = "us-east-1"

LANGUAGE_CONFIGS = {
    "Italian": {"voice": "Beatrice", "code": "it-IT", "engine": "generative"},
    "Spanish": {"voice": "Lucia", "code": "es-ES", "engine": "generative"},
    "French": {"voice": "Ambre", "code": "fr-FR", "engine": "generative"},
    "German": {"voice": "Lennart", "code": "de-DE", "engine": "generative"},
    "Japanese": {"voice": "Mizuki", "code": "ja-JP", "engine": "neural"},
}

def verify_api_keys(gemini_key: str, aws_access: str, aws_secret: str) -> dict:
    results = {"gemini": False, "aws": False, "error": None}
    
    # Test Gemini
    try:
        if not gemini_key:
            raise ValueError("No Gemini key provided.")
        client = genai.Client(api_key=gemini_key)
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="hi",
            config=types.GenerateContentConfig(max_output_tokens=1)
        )
        results["gemini"] = True
    except Exception as e:
        results["error"] = f"Gemini Error: {str(e)}"
        return results

    # Test AWS
    try:
        if not aws_access or not aws_secret:
            raise ValueError("No AWS keys provided.")
        polly = boto3.client(
            "polly",
            region_name=AWS_REGION,
            aws_access_key_id=aws_access,
            aws_secret_access_key=aws_secret,
        )
        polly.describe_voices(LanguageCode='en-US')
        results["aws"] = True
    except Exception as e:
        results["error"] = f"AWS Error: {str(e)}"
        
    return results
# ============================================================
# 3. Ask Gemini for structured content
# ============================================================

# ============================================================
# 4. Step 1: ask Gemini for structured content
# ============================================================

# ============================================================
# 5. Step 2: ask Polly to record the example sentence
# ============================================================
def generate_content(word: str, language: str, gemini_api_key: str, custom_prompt: str = None, translation_lang: str = "Both (English + Persian)") -> dict:
    if not gemini_api_key:
        return {"error": "Missing Gemini API Key."}
        
    gemini = genai.Client(api_key=gemini_api_key)
    
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
    # The return format depends on the client. For json it's returned as a text string that we parse.
    return json.loads(response.text)

#======================
def generate_audio(text: str, voice: str, lang_code: str, aws_access_key: str, aws_secret_key: str, engine: str = "neural") -> bytes:
    if not aws_access_key or not aws_secret_key:
        raise ValueError("Missing AWS credentials.")
        
    polly = boto3.client(
        "polly",
        region_name=AWS_REGION,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
    )
    
    speech = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice,
        Engine=engine,        
        LanguageCode=lang_code,
    )
    return speech["AudioStream"].read()

# ============================================================
# 4. Orchestrator: one word, top to bottom
# ============================================================
def process_word(user_input: str, language: str, api_keys: dict, custom_prompt: str = None, translation_lang: str = "Both (English + Persian)"):
    user_input = user_input.strip()
    print(f"→ {user_input} ({language})")
    try:
        # Force flush WSGI/Nginx buffers with 1024 bytes of empty space
        yield ": " + (" " * 1024) + "\n\n"
        yield f"data: {json.dumps({'status': f'🧠 Asking Gemini to translate {user_input}...'})}\n\n"
        # 1. Ask Gemini to generate the content based on the prompt
        data = generate_content(user_input, language, api_keys.get("gemini"), custom_prompt=custom_prompt, translation_lang=translation_lang)
        
        # 2. Check if Gemini rejected the word (e.g. wrong language)
        if data.get("error"):
            print(f"   ❌ Gemini error: {data['error']}")
            yield f"data: {json.dumps({'error': data['error']})}\n\n"
            return
        
        config = LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["Italian"])
        voice = config["voice"]
        lang_code = config["code"]
        engine = config.get("engine", "neural")

        is_verb = bool(data["conjugation_field"])
        print(f"   Gemini: word={data['word']}, verb={'yes' if is_verb else 'no'}")

        yield f"data: {json.dumps({'status': f'🗣️ Synthesizing {language} audio with AWS Polly...'})}\n\n"

        # always need word audio + example audio
        aws_kwargs = {
            "aws_access_key": api_keys.get("aws_access"),
            "aws_secret_key": api_keys.get("aws_secret"),
            "engine": engine
        }
        
        audios = {
            "":         generate_audio(data["tts_word"], voice, lang_code, **aws_kwargs),
            "_example": generate_audio(data["tts_example"], voice, lang_code, **aws_kwargs),
        }

        # verbs need six more
        if is_verb:
            for i in range(1, 7):
                audios[f"_{i}"] = generate_audio(data[f"tts_verb_{i}"], voice, lang_code, **aws_kwargs)

        total = sum(len(b) for b in audios.values())
        print(f"   Polly:  {len(audios)} clips, {total:,} bytes")
        
        yield f"data: {json.dumps({'status': '📦 Compiling flashcard data...'})}\n\n"

        audios_b64 = {k: base64.b64encode(v).decode() for k, v in audios.items()}
        yield f"data: {json.dumps({'result': {'success': True, 'data': data, 'audios': audios_b64}})}\n\n"
    except Exception as e:
        error_msg = str(e)
        if "does not support the selected engine: generative" in error_msg:
            error_msg = f"AWS Polly Error: The voice '{voice}' does not support the 'generative' AI engine. Please update main.py to use 'neural' for {language}."
        print(f"   ❌ {error_msg}")
        yield f"data: {json.dumps({'error': error_msg})}\n\n"

