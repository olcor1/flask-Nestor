import pdfplumber
import pytesseract
from PIL import Image
import uuid
from datetime import datetime
import spacy
import re
from .anonymizer import anonymize_text
from .financial_utils import (
    detecter_section_pdf,
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

def extract_lines_from_page(page):
    """Extrait les lignes de texte d'une page, avec fallback si page.chars échoue."""
    try:
        # Méthode 1: Utilise les coordonnées des caractères (si disponibles)
        words = page.chars
        if words and 'y' in words[0]:  # Vérifie que les coordonnées existent
            current_words = []
            lines = []
            for char in words:
                if current_words and abs(char["y"] - current_words[-1]["y"]) > 5:
                    if current_words:
                        lines.append("".join([c["text"] for c in current_words]))
                        current_words = []
                if current_words and abs(char["x"] - current_words[-1]["x"]) > 5:
                    lines.append("".join([c["text"] for c in current_words]))
                    current_words = []
                current_words.append(char)
            if current_words:
                lines.append("".join([c["text"] for c in current_words]))
            return lines
    except:
        pass  # Si page.chars échoue, passe à la méthode 2

    # Méthode 2: Utilise extract_text() avec fallback OCR
    text = page.extract_text()
    if not text:
        try:
            img = page.to_image().original
            text = ocr_image(img)
        except:
            text = ""
    return text.split('\n') if text else []

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
            lines = extract_lines_from_page(page)
            page_text = "\n".join(lines)
            full_text += page_text + "\n"

            # Détecte les colonnes de montants (indices des colonnes avec des nombres)
            amount_columns = []
            for line in lines:
                parts = re.split(r'\s{2,}', line)
                for i, part in enumerate(parts):
                    if re.match(r'^\d[\d\s.,]*$', part.strip()):
                        if i not in amount_columns:
                            amount_columns.append(i)

            # Associe les libellés aux montants
            current_section = None
            for line in lines:
                line_upper = line.upper()
                if "PRODUITS" in line_upper:
                    current_section = "Produits"
                elif "CHARGES LOCATIVES" in line_upper:
                    current_section = "Charges locatives"

                parts = re.split(r'\s{2,}', line)
                if len(parts) > 0 and not parts[0][0].isdigit():  # Ligne avec libellé
                    poste = parts[0].strip()
                    montants = []
                    for col in sorted(amount_columns):
                        if col < len(parts):
                            montant_str = parts[col].replace(' ', '').replace(',', '.')
                            try:
                                montant = float(montant_str)
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
