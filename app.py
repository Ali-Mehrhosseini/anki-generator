from flask import Flask, request, jsonify, send_from_directory
from main import process_word
import os

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')



@app.route('/api/prompt', methods=['GET'])
def get_prompt():
    from main import SYSTEM_INSTRUCTION_TEMPLATE
    return jsonify({"prompt": SYSTEM_INSTRUCTION_TEMPLATE}), 200

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    word = data.get('word')
    deck_name = data.get('deckName')
    model_name = data.get('modelName')
    language = data.get('language', 'Italian')
    custom_prompt = data.get('prompt')
    translation_lang = data.get('translationLang', 'Both (English + Persian)')
    api_keys = data.get('apiKeys', {})
    
    if not word:
        return jsonify({"success": False, "error": "No word provided"}), 400
        
    result = process_word(word, language=language, api_keys=api_keys, custom_prompt=custom_prompt, translation_lang=translation_lang)
    
    if result.get("success"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
