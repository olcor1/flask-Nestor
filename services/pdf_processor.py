import pdfplumber
import pytesseract
from PIL import Image
import uuid
from datetime import datetime
import spacy
import re
from .anonymizer import anonymize_text
from .financial_utils import (
    detecter_date_complete,
    detecter_annee_etats,
    detecter_type_etats_financiers
)

# Charge le modèle spaCy
nlp = spacy.load("fr_core_news_md")

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except:
        return ""

def generer_id_unique(prefix: str = "ENT") -> str:
    """Génère un ID unique pour l'entreprise."""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

def clean_montant(text):
    """Nettoie un montant (ex: '155 780$' → 155780.0)."""
    if not text:
        return None
    text = re.sub(r'[^\d.,]', '', text.strip())
    try:
        return float(text.replace(',', '.')) if text else None
    except:
        return None

def find_column_positions(page):
    """Trouve les positions X des colonnes en analysant les 5 premières lignes."""
    words = page.chars  # Tous les caractères avec leurs positions X/Y

    # Trouve la position X maximale des mots de la 1ère colonne (sans chiffres)
    max_x_first_col = 0
    longest_poste = {"text": "", "x_end": 0}

    # Trouve les positions X des "$" pour les colonnes de montants
    dollar_positions = []

    for char in words:
        if char["text"].isdigit() or char["text"] == "$":
            if char["text"] == "$":
                dollar_positions.append(char["x0"])
        else:
            # Trouve le mot le plus long (sans chiffres)
            if not any(c.isdigit() for c in char["text"]):
                word_length = len(char["text"].strip())
                word_x_end = char["x1"]
                if word_x_end > max_x_first_col and word_length > len(longest_poste["text"]):
                    max_x_first_col = word_x_end
                    longest_poste = {"text": char["text"].strip(), "x_end": word_x_end}

    # Détermine les positions X des colonnes
    first_col_end = max_x_first_col if max_x_first_col > 0 else 200  # Valeur par défaut
    second_col_end = min(dollar_positions) if dollar_positions else first_col_end + 100

    return {
        "longest_poste": longest_poste,
        "first_col_end": first_col_end,
        "dollar_positions": dollar_positions,
        "second_col_end": second_col_end
    }

def extract_words_in_range(page, x_start, x_end):
    """Extrait le texte dans une plage de positions X."""
    words = page.chars
    text_parts = []

    for char in words:
        if x_start <= char["x0"] <= x_end:
            text_parts.append(char["text"])

    return "".join(text_parts).strip()

def parse_financial_page(page):
    """Parse une page financière en utilisant les positions X."""
    column_info = find_column_positions(page)
    data = {
        "sections": [],
        "postes": [],
        "totaux": [],
        "debug_info": {
            "longest_poste": column_info["longest_poste"],
            "first_col_end": column_info["first_col_end"],
            "dollar_positions": column_info["dollar_positions"],
            "second_col_end": column_info["second_col_end"]
        }
    }

    current_section = None
    words = page.chars
    lines = {}

    # Regroupe les caractères en lignes (par position Y)
    for char in words:
        y = round(char["top"], 1)
        if y not in lines:
            lines[y] = []
        lines[y].append(char)

    # Traite chaque ligne
    for y, chars_in_line in sorted(lines.items()):
        line_text = "".join([c["text"] for c in chars_in_line]).strip()
        if not line_text:
            continue

        # Détection des sections (lignes sans montants)
        if not re.search(r'\d', line_text):
            if any(section in line_text.upper() for section in ["PRODUITS", "CHARGES", "ACTIF", "PASSIF", "BÉNÉFICE"]):
                current_section = line_text
                data["sections"].append({
                    "nom": current_section,
                    "y_position": y
                })
            continue

        # Extrait les données en utilisant les positions X
        poste = extract_words_in_range(page, 0, column_info["first_col_end"])
        montant1 = extract_words_in_range(page, column_info["first_col_end"], column_info["second_col_end"])
        montant2 = extract_words_in_range(page, column_info["second_col_end"], page.width)

        montant1_clean = clean_montant(montant1)
        montant2_clean = clean_montant(montant2)

        if poste and (montant1_clean is not None or montant2_clean is not None):
            is_total = poste.upper().startswith(("BÉNÉFICE", "TOTAL", "SOMME"))

            data["postes"].append({
                "poste": poste,
                "montant1": montant1_clean,
                "montant2": montant2_clean,
                "est_total": is_total,
                "section": current_section,
                "y_position": y
            })

            if is_total:
                data["totaux"].append({
                    "poste": poste,
                    "montant1": montant1_clean,
                    "montant2": montant2_clean,
                    "section": current_section,
                    "y_position": y
                })

    return data

def process_pdf(file):
    """Traite le PDF en utilisant les coordonnées X pour les colonnes."""
    with pdfplumber.open(file) as pdf:
        full_text = ""
        result = {
            "metadata": {},
            "pages": [],
            "debug_info": {}
        }

        entreprise_id = generer_id_unique()

        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            parsed_page = parse_financial_page(page)
            parsed_page["page_num"] = page_num + 1
            result["pages"].append(parsed_page)

            # Met à jour les infos de debug globales
            if "debug_info" in parsed_page:
                result["debug_info"].update(parsed_page["debug_info"])

        # Métadonnées
        first_page_text = pdf.pages[0].extract_text() or ocr_image(pdf.pages[0].to_image().original)
        doc = nlp(first_page_text)
        company_name = next((ent.text for ent in doc.ents if ent.label_ == "ORG"), "[ENTREPRISE]")

        ef_info = detecter_type_etats_financiers(first_page_text)
        annee_etats = detecter_annee_etats(first_page_text)
        date_complete = detecter_date_complete(first_page_text)

        result["metadata"] = {
            "entreprise_id": entreprise_id,
            "nom_entreprise_anonymise": company_name,
            "annee_etats_financiers": annee_etats,
            "date_etats_financiers": date_complete,
            "type_etats_financiers": ef_info["type"],
            "est_consolide": ef_info["consolide"],
            "date_extraction": datetime.now().strftime("%Y-%m-%d"),
            "source": file.filename
        }

        return result
