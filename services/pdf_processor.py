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

def find_column_positions(page):
    """Trouve les positions X des colonnes en analysant les caractères."""
    words = page.chars  # Tous les caractères avec leurs positions X/Y

    # Trouve la position X maximale des mots de la 1ère colonne (sans chiffres)
    max_x_first_col = 0
    longest_poste = {"text": "", "x_end": 0}

    # Trouve les positions X des "$" pour les colonnes de montants
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

    # Parcourir les mots pour trouver le plus long et les positions des "$"
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
        "first_col_end": first_col_end,
        "second_col_end": second_col_end
    }

def parse_financial_page(page):
    """Parse une page financière en utilisant les positions X."""
    # Obtenir les positions des colonnes pour cette page
    column_info = find_column_positions(page)
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
        return table
    except Exception as e:
        print(f"Failed to extract table: {e}")
        return None

def process_pdf(file):
    """Traite le PDF en utilisant les coordonnées X pour les colonnes."""
    with pdfplumber.open(file) as pdf:
        full_text = ""
        comptes = []
        entreprise_id = generer_id_unique()

        # 1. Première page : métadonnées
        first_page = pdf.pages[0]
        first_page_text = first_page.extract_text() or ocr_image(first_page.to_image().original)
        doc = nlp(first_page_text)
        company_name = next((ent.text for ent in doc.ents if ent.label_ == "ORG"), "[ENTREPRISE]")

        ef_info = detecter_type_etats_financiers(first_page_text)
        annee_etats = detecter_annee_etats(first_page_text)
        date_complete = detecter_date_complete(first_page_text)

        # 2. Traite chaque page
        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            # Analyser la page financière
            table = parse_financial_page(page)
            if table:
                for row in table:
                    if len(row) >= 3:  # Assurez-vous que la ligne a au moins 3 colonnes
                        poste, montant1, montant2 = row[0], row[1], row[2]
                        poste = poste.strip()
                        montant1 = montant1.strip()
                        montant2 = montant2.strip()

                        # Nettoyer les montants
                        montant1_clean = None
                        montant2_clean = None
                        if montant1:
                            montant1_clean = float(re.sub(r'[^\d.,]', '', montant1).replace(',', '.')) if re.sub(r'[^\d.,]', '', montant1) else None
                        if montant2:
                            montant2_clean = float(re.sub(r'[^\d.,]', '', montant2).replace(',', '.')) if re.sub(r'[^\d.,]', '', montant2) else None

                        if poste and (montant1_clean is not None or montant2_clean is not None):
                            comptes.append({
                                "id": f"CPT_{uuid.uuid4().hex[:8].upper()}",
                                "nom": poste,
                                "etat": "etat_des_resultats",
                                "section": None,
                                "montant_annee_courante": montant1_clean,
                                "montant_annee_precedente": montant2_clean,
                                "reference_annexe": None,
                                "page_source": page_num + 1
                            })

        return {
            "metadata": {
                "entreprise_id": entreprise_id,
                "nom_entreprise_anonymise": company_name,
                "annee_etats_financiers": annee_etats,
                "date_etats_financiers": date_complete,
                "type_etats_financiers": ef_info["type"],
                "est_consolide": ef_info["consolide"],
                "date_extraction": datetime.now().strftime("%Y-%m-%d"),
                "source": file.filename
            },
            "comptes": comptes,
            "annexes": [],
            "texte_complet_anonymise": anonymize_text(full_text, company_name)
        }

