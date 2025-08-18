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

def process_pdf(file):
    """Traite le PDF et extrait les comptes avec montants pour 2 années."""
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

            # Extrait les lignes de texte
            lines = page_text.split('\n')

            # Détecte la section actuelle (Produits, Charges, etc.)
            current_section = None

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

                # Cherche les lignes avec des montants (ex: "Assurances 963 842")
                if re.search(r'\d[\d\s.,]+', line):
                    # Séparation des parties par espaces multiples
                    parts = re.split(r'\s{2,}', line.strip())

                    if len(parts) >= 2:
                        # La première partie est le libellé
                        poste = parts[0].strip()

                        # Les parties suivantes sont les montants
                        montants = []
                        for part in parts[1:]:
                            montant_str = re.sub(r'[^\d.,]', '', part.strip())
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
