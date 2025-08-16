import os
from flask import Flask, request, jsonify
import pdfplumber
import io
import pytesseract

app = Flask("Plumber pour EFs")

API_KEY = os.getenv("FLASK_API_KEY")

@app.before_request
def check_api_key():
    key = request.headers.get("x-api-key")
    if API_KEY and key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    extracted_data = []

    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:  # s'assure que ce n'est pas None
                    # Ajouter séparateur pour lisibilité
                    extracted_data.append(f"--- Page {i+1} ---\n{text}")

        # Concaténer uniquement si la liste n'est pas vide
        all_text = "\n\n".join(extracted_data) if extracted_data else "No text found in PDF"

        return jsonify({"extracted_text": all_text})

    except Exception as e:
        # Capture les erreurs de pdfplumber ou du PDF
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return "Bravo Oli!"

@app.route("/tesseract-test")
def tesseract_test():
    try:
        version = pytesseract.get_tesseract_version()
        return jsonify({"tesseract_version": str(version)})
    except Exception as e:
        return jsonify({"error": str(e)})
