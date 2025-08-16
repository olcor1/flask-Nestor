import os
from flask import Flask, request, jsonify
import pdfplumber
import io

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

   with pdfplumber.open(io.BytesIO(file.read())) as pdf:
    extracted_data = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text:
            extracted_data.append(f"--- Page {i+1} ---\n{text}")

# Concaténer pour affichage plus lisible
all_text = "\n\n".join(extracted_data)

return jsonify({"extracted_text": all_text})


@app.route("/")
def home():
    return "Bravo Oli!"
