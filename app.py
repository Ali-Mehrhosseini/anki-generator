from flask import Flask, request, jsonify, send_from_directory, Response
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

@app.route('/api/verify-keys', methods=['POST'])
def verify_keys():
    from main import verify_api_keys
    data = request.json
    api_keys = data.get('apiKeys', {})
    gemini_key = api_keys.get('gemini', '')
    aws_access = api_keys.get('aws_access', '')
    aws_secret = api_keys.get('aws_secret', '')
    
    result = verify_api_keys(gemini_key, aws_access, aws_secret)
    return jsonify(result), 200

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    word = data.get('word')
    language = data.get('language', 'Italian')
    custom_prompt = data.get('prompt')
    translation_lang = data.get('translationLang', 'Both (English + Persian)')
    api_keys = data.get('apiKeys', {})
    
    if not word:
        import json
        return Response(f"data: {json.dumps({'error': 'No word provided'})}\n\n", mimetype='text/event-stream')
        
    return Response(
        process_word(word, language=language, api_keys=api_keys, custom_prompt=custom_prompt, translation_lang=translation_lang),
        mimetype='text/event-stream',
        headers={
            'X-Accel-Buffering': 'no',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)
