from flask import Flask, request, jsonify, send_from_directory
from main import process_word, check_anki_status, get_anki_info
import os

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/status', methods=['GET'])
def status():
    is_online = check_anki_status()
    return jsonify({"status": "online" if is_online else "offline"}), 200

@app.route('/api/anki-info', methods=['GET'])
def anki_info():
    info = get_anki_info()
    if info.get("success"):
        return jsonify(info), 200
    else:
        return jsonify(info), 500

@app.route('/api/prompt', methods=['GET'])
def get_prompt():
    from main import SYSTEM_INSTRUCTION_TEMPLATE
    return jsonify({"prompt": SYSTEM_INSTRUCTION_TEMPLATE}), 200

@app.route('/api/check_duplicate', methods=['POST'])
def check_duplicate_route():
    data = request.json
    word = data.get('word')
    deck_name = data.get('deckName')
    
    if not word or not deck_name:
        return jsonify({"duplicate": False}), 200
        
    from main import check_duplicate
    is_dup = check_duplicate(word, deck_name)
    return jsonify({"duplicate": is_dup}), 200

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    word = data.get('word')
    deck_name = data.get('deckName')
    model_name = data.get('modelName')
    language = data.get('language', 'Italian')
    custom_prompt = data.get('prompt')
    translation_lang = data.get('translationLang', 'Both (English + Persian)')
    
    if not word:
        return jsonify({"success": False, "error": "No word provided"}), 400
        
    result = process_word(word, target_deck=deck_name, target_model=model_name, language=language, custom_prompt=custom_prompt, translation_lang=translation_lang)
    
    if result.get("success"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
