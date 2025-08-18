import pdfplumber
import camelot
import pandas as pd
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

def process_pdf(file):
    """Traite le PDF avec Camelot pour extraire les tableaux."""
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

        # 2. Utilise Camelot pour extraire les tableaux
        tables = camelot.read_pdf(file, flavor='stream', pages='all')

        # 3. Traite chaque tableau
        current_section = None
        for table in tables:
            df = table.df  # DataFrame pandas du tableau

            # Détecte la section à partir de la première ligne du tableau
            first_row = df.iloc[0, 0] if not df.empty else ""
            if pd.notna(first_row):
                first_row_upper = str(first_row).upper()
                if "PRODUITS" in first_row_upper:
                    current_section = "Produits"
                elif "CHARGES" in first_row_upper:
                    current_section = "Charges locatives"
                elif "BÉNÉFICE" in first_row_upper:
                    current_section = "Bénéfice"

            # Parcourt les lignes du tableau (en ignorant l'en-tête)
            for _, row in df.iterrows():
                # Ignore les lignes vides ou les en-têtes
                if row.isna().all() or pd.isna(row.iloc[0]):
                    continue

                # La première colonne = libellé, les suivantes = montants
                poste = str(row.iloc[0]).strip()
                if not poste or poste.upper() in ["PRODUITS", "CHARGES LOCATIVES", "TOTAL", "BÉNÉFICE"]:
                    continue

                # Extrait les montants des colonnes suivantes
                montants = []
                for value in row.iloc[1:]:
                    if pd.notna(value):
                        montant_str = re.sub(r'[^\d.,]', '', str(value))
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
                        "page_source": table.page  # Numéro de page
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
