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
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                extracted_data.append(text)

    return jsonify({"pages": extracted_data})

@app.route("/")
def home():
    return "Bravo Oli!"
