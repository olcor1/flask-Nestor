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

def detect_financial_page(lines):
    """Détecte si une page est une page financière (contient des montants)."""
    for line in lines[:10]:  # Vérifie les 10 premières lignes
        if re.search(r'\d[\d\s.,]+\s*\$\s*\d[\d\s.,]+', line):
            return True
    return False

def parse_financial_page(page_text):
    """Parse une page financière en sections, postes et totaux."""
    lines = page_text.split('\n')
    data = {
        "sections": [],
        "postes": [],
        "totaux": [],
        "debug_info": {
            "longest_term": {"term": "", "position": 0},
            "first_montant_line": None
        }
    }

    current_section = None
    in_section = False

    for line_num, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Détection du type d'état (première ligne avec des mots clés)
        if line_num == 0:
            if "ÉTAT DES RÉSULTATS" in line.upper():
                data["type_etat"] = "etat_des_resultats"
            elif "BILAN" in line.upper():
                data["type_etat"] = "bilan"
            else:
                data["type_etat"] = "inconnu"

        # Détection des sections (lignes sans montants)
        if not re.search(r'\d', line):
            if any(section in line.upper() for section in ["PRODUITS", "CHARGES", "ACTIF", "PASSIF", "BÉNÉFICE"]):
                current_section = line
                in_section = True
                data["sections"].append({
                    "nom": current_section,
                    "ligne": line_num
                })
            continue

        # Détection de la première ligne avec montants (pour debug)
        if data["debug_info"]["first_montant_line"] is None and re.search(r'\d[\d\s.,]+\s*\$\s*\d[\d\s.,]+', line):
            data["debug_info"]["first_montant_line"] = {
                "ligne": line,
                "position": line_num
            }

        # Trouve le plus long terme (pour debug)
        words = re.findall(r'[^\d\s]+', line)
        for word in words:
            if len(word) > len(data["debug_info"]["longest_term"]["term"]):
                data["debug_info"]["longest_term"] = {
                    "term": word,
                    "position": line.find(word)
                }

        # Détection des postes (lignes avec 2 montants)
        if re.search(r'\d[\d\s.,]+\s*\$\s*\d[\d\s.,]+', line):
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 3:
                poste = parts[0].strip()
                montant1 = clean_montant(parts[1])
                montant2 = clean_montant(parts[2])

                # Vérifie si c'est un total (commence par "Bénéfice", "Total", etc.)
                is_total = poste.upper().startswith(("BÉNÉFICE", "TOTAL", "SOMME"))

                data["postes"].append({
                    "ligne": line_num,
                    "poste": poste,
                    "montant1": montant1,
                    "montant2": montant2,
                    "est_total": is_total,
                    "section": current_section
                })

                if is_total:
                    data["totaux"].append({
                        "ligne": line_num,
                        "poste": poste,
                        "montant1": montant1,
                        "montant2": montant2,
                        "section": current_section
                    })

    return data

def process_pdf(file):
    """Traite le PDF en détectant les pages financières et en les parsant."""
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

            if detect_financial_page(page_text.split('\n')):
                parsed_page = parse_financial_page(page_text)
                parsed_page["page_num"] = page_num + 1
                result["pages"].append(parsed_page)

                # Met à jour les infos de debug globales
                if "debug_info" in parsed_page:
                    result["debug_info"].update({
                        "longest_term": parsed_page["debug_info"]["longest_term"],
                        "first_montant_line": parsed_page["debug_info"]["first_montant_line"]
                    })

        # 1. Première page : métadonnées
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
