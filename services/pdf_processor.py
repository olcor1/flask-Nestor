import pdfplumber
import pytesseract
from PIL import Image
import uuid
from datetime import datetime
import spacy
import re
import logging
import os
import json
from werkzeug.datastructures import FileStorage

# Configure logging to capture logs in a list
logs = []

class ListHandler(logging.Handler):
    def __init__(self, log_list):
        super().__init__()
        self.log_list = log_list

    def emit(self, record):
        self.log_list.append(self.format(record))

# Create a custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = ListHandler(logs)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load spaCy model
try:
    nlp = spacy.load("fr_core_news_md")
except Exception as e:
    logger.error(f"Failed to load spaCy model: {e}")
    raise

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""

def generer_id_unique(prefix: str = "ENT") -> str:
    """Génère un ID unique pour l'entreprise."""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

def clean_montant(text):
    """Nettoie un montant (ex: '155 780\$' → 155780.0)."""
    if not text:
        return None
    text = re.sub(r'[^\d.,]', '', text.strip())
    try:
        return float(text.replace(',', '.')) if text else None
    except:
        return None

def find_column_positions(page):
    """Trouve les positions X des colonnes en analysant les caractères."""
    words = page.chars  # Tous les caractères avec leurs positions X/Y

    # Trouve la position X maximale des mots de la 1ère colonne (sans chiffres)
    max_x_first_col = 0
    longest_poste = {"text": "", "x_end": 0}

    # Trouve les positions X des "\$" pour les colonnes de montants
    dollar_positions = []

    # Regrouper les caractères en mots
    words_in_page = []
    current_word = []
    prev_char = None

    for char in sorted(words, key=lambda c: (c["top"], c["x0"])):
        if prev_char and abs(char["x0"] - prev_char["x1"]) < 5:  # Seuil de proximité pour les caractères d'un même mot
            current_word.append(char)
        else:
            if current_word:
                words_in_page.append(current_word)
                current_word = []
            current_word.append(char)
        prev_char = char

    if current_word:
        words_in_page.append(current_word)

    # Parcourir les mots pour trouver le plus long et les positions des "\$"
    for word_chars in words_in_page:
        word_text = "".join([c["text"] for c in word_chars]).strip()
        word_x_end = max(c["x1"] for c in word_chars)

        if not any(c.isdigit() for c in word_text):  # Ignore les mots avec des chiffres (montants)
            if word_x_end > max_x_first_col and len(word_text) > len(longest_poste["text"]):
                max_x_first_col = word_x_end
                longest_poste = {"text": word_text, "x_end": word_x_end}

        if "$" in word_text:
            for char in word_chars:
                if char["text"] == "$":
                    dollar_positions.append(char["x0"])

    # Détermine les positions X des colonnes
    first_col_end = max_x_first_col if max_x_first_col > 0 else 200  # Valeur par défaut
    second_col_end = min(dollar_positions) if dollar_positions else first_col_end + 100

    return {
        "longest_poste": longest_poste,
        "first_col_end": first_col_end,
        "dollar_positions": dollar_positions,
        "second_col_end": second_col_end
    }

def parse_financial_page(page, column_info):
    """Parse une page financière en utilisant les positions X."""
    first_col_end = column_info["first_col_end"]
    second_col_end = column_info["second_col_end"]

    # Définir les colonnes explicitement
    table_settings = {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "text",
        "explicit_vertical_lines": [0, first_col_end, second_col_end, page.width]
    }

    # Extraire le tableau avec les colonnes définies
    try:
        table = page.extract_table(table_settings)
    except Exception as e:
        logger.error(f"Failed to extract table: {e}")
        return {
            "sections": [],
            "postes": [],
            "totaux": [],
            "debug_info": column_info
        }

    data = {
        "sections": [],
        "postes": [],
        "totaux": [],
        "debug_info": column_info
    }

    current_section = None

    if table:
        for row in table:
            if len(row) >= 3:  # Assurez-vous que la ligne a au moins 3 colonnes
                poste, montant1, montant2 = row[0], row[1], row[2]
                poste = poste.strip()
                montant1 = montant1.strip()
                montant2 = montant2.strip()

                montant1_clean = clean_montant(montant1)
                montant2_clean = clean_montant(montant2)

                # Détection des sections (lignes sans montants)
                if not montant1_clean and not montant2_clean:
                    if any(section in poste.upper() for section in ["PRODUITS", "CHARGES", "ACTIF", "PASSIF", "BÉNÉFICE"]):
                        current_section = poste
                        data["sections"].append({
                            "nom": current_section,
                            "y_position": None  # On ne peut pas obtenir la position Y directement ici
                        })
                    continue

                if poste and (montant1_clean is not None or montant2_clean is not None):
                    is_total = poste.upper().startswith(("BÉNÉFICE", "TOTAL", "SOMME"))

                    data["postes"].append({
                        "poste": poste,
                        "montant1": montant1_clean,
                        "montant2": montant2_clean,
                        "est_total": is_total,
                        "section": current_section,
                        "y_position": None  # On ne peut pas obtenir la position Y directement ici
                    })

                    if is_total:
                        data["totaux"].append({
                            "poste": poste,
                            "montant1": montant1_clean,
                            "montant2": montant2_clean,
                            "section": current_section,
                            "y_position": None  # On ne peut pas obtenir la position Y directement ici
                        })

    return data

def process_pdf(file_path):
    """Traite le PDF en utilisant les coordonnées X pour les colonnes."""
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return {"status": "error", "message": f"File not found: {file_path}", "logs": logs}

        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            result = {
                "metadata": {},
                "pages": [],
                "debug_info": {},
                "logs": []
            }

            entreprise_id = generer_id_unique()

            for page_num, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text() or ocr_image(page.to_image().original)
                    full_text += page_text + "\n"

                    # Obtenir les positions des colonnes pour cette page
                    column_info = find_column_positions(page)

                    # Analyser la page financière
                    parsed_page = parse_financial_page(page, column_info)
                    parsed_page["page_num"] = page_num + 1
                    result["pages"].append(parsed_page)

                    # Met à jour les infos de debug globales
                    if "debug_info" in parsed_page:
                        result["debug_info"].update(parsed_page["debug_info"])
                except Exception as e:
                    logger.error(f"Failed to process page {page_num}: {e}")
                    continue

            # Métadonnées
            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text() or ocr_image(pdf.pages[0].to_image().original)
                doc = nlp(first_page_text)
                company_name = next((ent.text for ent in doc.ents if ent.label_ == "ORG"), "[ENTREPRISE]")

                ef_info = detect
