from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from services.pdf_processor import process_pdf

load_dotenv()
app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("La clé API n'est pas configurée.")

@app.before_request
def verify_api_key():
    if request.endpoint != 'health_check' and request.headers.get('X-API-KEY') != API_KEY:
        return jsonify({"error": "Clé API invalide"}), 401

@app.route('/health_check')
def health_check():
    return jsonify({"status": "OK"})

@app.route('/anonymize', methods=['POST'])
def anonymize_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier fourni"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom de fichier vide"}), 400
    try:
        result = process_pdf(file)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
