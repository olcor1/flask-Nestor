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
    text = re.sub(r'[^\d]', '', text.strip())  # Garde seulement les chiffres
    try:
        return float(text) if text else None
    except:
        return None

def process_pdf(file):
    """Traite le PDF en extrayant directement les lignes avec des montants."""
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
        current_section = None
        for page in pdf.pages:
            page_text = page.extract_text() or ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            # 3. Extrait les lignes avec des montants
            lines = page_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Détecte les sections
                if line.upper().startswith("PRODUITS"):
                    current_section = "Produits"
                    continue
                elif line.upper().startswith("CHARGES"):
                    current_section = "Charges locatives"
                    continue
                elif line.upper().startswith("BÉNÉFICE"):
                    current_section = "Bénéfice"
                    continue

                # Cherche les lignes avec des montants (ex: "Assurances 963 842")
                match = re.match(r'^(.*?)\s+(\d[\d\s.,]*)\s+(\d[\d\s.,]*)$', line)
                if match:
                    poste = match.group(1).strip()
                    montant_2020 = clean_montant(match.group(2))
                    montant_2019 = clean_montant(match.group(3))

                    if poste and (montant_2020 is not None or montant_2019 is not None):
                        poste_anonymise = anonymize_text(poste, company_name)
                        comptes.append({
                            "id": f"CPT_{uuid.uuid4().hex[:8].upper()}",
                            "nom": poste_anonymise,
                            "etat": "etat_des_resultats",
                            "section": current_section or "Autre",
                            "montant_annee_courante": montant_2020,
                            "montant_annee_precedente": montant_2019,
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
