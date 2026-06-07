from flask import Flask, request, jsonify, send_from_directory
from main import process_word, check_anki_status
import os

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/status', methods=['GET'])
def status():
    is_online = check_anki_status()
    return jsonify({"status": "online" if is_online else "offline"}), 200

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    word = data.get('word')
    
    if not word:
        return jsonify({"success": False, "error": "No word provided"}), 400
        
    result = process_word(word)
    
    if result.get("success"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
