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

def extract_tables_with_fallback(pdf_path):
    """Essaie différentes configurations pour extraire les tableaux."""
    table_configurations = [
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},  # Bordures claires
        {"vertical_strategy": "text", "horizontal_strategy": "text"},   # Alignement texte
        {"vertical_strategy": "explicit", "horizontal_strategy": "explicit"},  # Explicite
        {"vertical_strategy": "lines_strict", "horizontal_strategy": "lines_strict"}  # Strict
    ]

    best_tables = []
    for config in table_configurations:
        with pdfplumber.open(pdf_path) as pdf:
            tables = []
            for page in pdf.pages:
                extracted_tables = page.extract_tables(config)
                if extracted_tables:
                    tables.extend(extracted_tables)
            if tables:
                best_tables = tables
                break  # Utilise la première configuration qui fonctionne

    return best_tables

def process_pdf(file):
    """Traite le PDF avec fallback automatique pour les tableaux."""
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

        # 2. Extrait les tableaux avec fallback automatique
        tables = extract_tables_with_fallback(file)

        # 3. Traite chaque tableau
        current_section = None
        for table in tables:
            for row in table:
                if not row:
                    continue

                # Détecte les sections
                first_cell = row[0].strip().upper() if row else ""
                if "PRODUITS" in first_cell:
                    current_section = "Produits"
                    continue
                elif "CHARGES" in first_cell:
                    current_section = "Charges locatives"
                    continue
                elif "BÉNÉFICE" in first_cell:
                    current_section = "Bénéfice"
                    continue

                # Ignore les lignes vides ou les en-têtes
                if not row[0] or row[0].strip().upper() in ["TOTAL", "BÉNÉFICE D'EXPLOITATION", "BÉNÉFICE AVANT IMPÔTS"]:
                    continue

                # Extrait les montants
                poste = row[0].strip()
                montants = []
                for value in row[1:]:
                    if isinstance(value, str):
                        montant_str = re.sub(r'[^\d.,]', '', value.strip())
                        if montant_str:
                            try:
                                montant = float(montant_str.replace(',', '.'))
                                montants.append(montant)
                            except:
                                continue

                if montants and poste:
                    poste_anonymise = anonymize_text(poste, company_name)
                    comptes.append({
                        "id": f"CPT_{uuid.uuid4().hex[:8].upper()}",
                        "nom": poste_anonymise,
                        "etat": "etat_des_resultats",
                        "section": current_section or "Autre",
                        "montant_annee_courante": montants[0] if len(montants) > 0 else None,
                        "montant_annee_precedente": montants[1] if len(montants) > 1 else None,
                        "reference_annexe": None,
                        "page_source": pdf.pages.index(pdf.pages[0]) + 1  # À ajuster si multi-pages
                    })

        # 4. Retourne le JSON final
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
