import pdfplumber
import pytesseract
from PIL import Image
import uuid
from datetime import datetime
from .anonymizer import anonymize_text
from .financial_utils import (
    detecter_section,
    extraire_montants_annees,
    detecter_reference_annexe,
    detecter_type_etats_financiers,
    detecter_annee_etats
)

def ocr_image(image):
    return pytesseract.image_to_string(image, lang='fra+eng')

def generer_id_unique(prefix: str = "ENT") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

def process_pdf(file):
    with pdfplumber.open(file) as pdf:
        full_text = ""
        comptes = []
        annexes = []
        entreprise_id = generer_id_unique()
        total_pages = len(pdf.pages)

        # 1. Première page : métadonnées
        first_page_text = pdf.pages[0].extract_text() or ocr_image(pdf.pages[0].to_image().original)
        doc = nlp(first_page_text)
        company_name = next((ent.text for ent in doc.ents if ent.label_ == "ORG"), "[ENTREPRISE]")

        # Détecte type, consolidation et année
        ef_info = detecter_type_etats_financiers(first_page_text)
        annee_etats = detecter_annee_etats(first_page_text)

        # 2. Traite chaque page
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if not page_text.strip():
                page_text = ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            # 3. Extrait les tableaux
            tables = page.extract_tables()
            for table in tables:
                if len(table) < 2:
                    continue
                header = table[0][0].lower() if table else ""
                etat = None
                if any(kw in header for kw in ["actif", "passif"]):
                    etat = "bilan"
                elif any(kw in header for kw in ["résultat", "bénéfice", "chiffre d'affaires"]):
                    etat = "etat_des_resultats"
                elif any(kw in header for kw in ["bénéfices non répartis"]):
                    etat = "benefices_non_repartis"

                for row in table[1:]:
                    if len(row) >= 2:
                        poste = row[0].strip()
                        poste_anonymise = anonymize_text(poste, company_name)
                        montant_info = extraire_montants_annees(" ".join(row))
                        reference = detecter_reference_annexe(" ".join(row))

                        comptes.append({
                            "id": f"CPT_{uuid.uuid4().hex[:8].upper()}",
                            "nom": poste_anonymise,
                            "etat": etat,
                            "section": detecter_section(poste, etat),
                            "montant_annee_courante": montant_info["courant"],
                            "montant_annee_precedente": montant_info["precedent"],
                            "reference_annexe": reference,
                            "page_source": i + 1
                        })

            # 4. Détecte les annexes
            if "annexe" in page_text.lower():
                annexes.append({
                    "reference": detecter_reference_annexe(page_text) or f"ANNEXE_{i+1}",
                    "texte": anonymize_text(page_text, company_name),
                    "page": i + 1
                })

        # 5. Anonymise le texte complet
        anonymized_text = anonymize_text(full_text, company_name)

        return {
            "metadata": {
                "entreprise_id": entreprise_id,
                "nom_entreprise_anonymise": company_name,
                "annee_etats_financiers": annee_etats,
                "type_etats_financiers": ef_info["type"],
                "est_consolide": ef_info["consolide"],
                "date_extraction": datetime.now().strftime("%Y-%m-%d"),
                "source": file.filename
            },
            "comptes": comptes,
            "annexes": annexes,
            "texte_complet_anonymise": anonymized_text
        }
