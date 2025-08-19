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
    text = re.sub(r'[^\d]', '', text.strip())
    try:
        return float(text) if text else None
    except:
        return None

def determine_column_positions(page):
    """Première passe : Détermine les positions des colonnes et affiche des infos de débogage."""
    text = page.extract_text() or ocr_image(page.to_image().original)
    lines = text.split('\n')

    # Trouve la position maximale de la fin des mots dans la première colonne
    max_first_column_end = 0
    longest_word = ""
    dollar_positions = []

    for line in lines[:5]:  # Analyse les 5 premières lignes
        # Trouve la fin de la première colonne (position max des mots)
        words = re.findall(r'\S+', line)
        if words:
            for word in words:
                if not re.search(r'\d', word):  # Ignore les mots avec des chiffres (montants)
                    if len(word) > len(longest_word):
                        longest_word = word
            first_word_end = len(line.split('$')[0]) if '$' in line else len(line)
            if first_word_end > max_first_column_end:
                max_first_column_end = first_word_end

        # Trouve les positions des "$" pour les colonnes suivantes
        for match in re.finditer(r'\$', line):
            dollar_positions.append(match.start())

    # Affiche les infos de débogage
    print(f"Plus long mot de la première colonne: '{longest_word}' (longueur: {len(longest_word)})")
    print(f"Position de fin de la première colonne: {max_first_column_end}")
    print(f"Positions des '$' détectées: {dollar_positions}")

    # Détermine les positions des colonnes
    if dollar_positions:
        second_column_end = min(dollar_positions) if dollar_positions else max_first_column_end + 10
    else:
        second_column_end = max_first_column_end + 10

    print(f"Position de fin de la deuxième colonne: {second_column_end}")

    return max_first_column_end, second_column_end

def process_pdf(file):
    """Traite le PDF en deux passes : 1. Détermination des colonnes, 2. Extraction des données."""
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

        # 2. Première passe : Détermine les positions des colonnes
        first_page = pdf.pages[0]
        first_col_end, second_col_end = determine_column_positions(first_page)

        # 3. Deuxième passe : Extrait les données
        current_section = None
        for page in pdf.pages:
            page_text = page.extract_text() or ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            lines = page_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Détection automatique des sections
                if not any(c.isdigit() for c in line):  # Ligne sans chiffres = section probable
                    line_upper = line.upper()
                    if any(section in line_upper for section in ["PRODUITS", "CHARGES", "BÉNÉFICE"]):
                        current_section = line
                        print(f"Section détectée: {current_section}")
                        continue

                # Extrait les données en utilisant les positions des colonnes
                if len(line) > second_col_end:
                    poste = line[:first_col_end].strip()
                    montant_2020_part = line[first_col_end:second_col_end].strip()
                    montant_2019_part = line[second_col_end:].strip()

                    print(f"Ligne traitée: '{line}'")
                    print(f"  Libellé: '{poste}'")
                    print(f"  Montant 2020: '{montant_2020_part}'")
                    print(f"  Montant 2019: '{montant_2019_part}'")

                    montant_2020 = clean_montant(montant_2020_part)
                    montant_2019 = clean_montant(montant_2019_part)

                    montants = []
                    if montant_2020 is not None:
                        montants.append(montant_2020)
                    if montant_2019 is not None:
                        montants.append(montant_2019)

                    if poste and montants:
                        poste_anonymise = anonymize_text(poste, company_name)
                        comptes.append({
                            "id": f"CPT_{uuid.uuid4().hex[:8].upper()}",
                            "nom": poste_anonymise,
                            "etat": "etat_des_resultats",
                            "section": current_section or "Autre",
                            "montant_annee_courante": montants[0] if len(montants) > 0 else None,
                            "montant_annee_precedente": montants[1] if len(montants) > 1 else None,
                            "reference_annexe": None,
                            "page_source": pdf.pages.index(page) + 1
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
