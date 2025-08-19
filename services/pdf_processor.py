import pdfplumber
import pytesseract
from PIL import Image
import spacy
import re
import json

nlp = spacy.load("fr_core_news_md")

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception:
        return ""

def parse_ligne(ligne):
    """
    Parse une ligne de texte pour extraire le poste, le montant année courante et le montant année précédente.

    Gère les montants vides représentés par "-", les montants négatifs entre parenthèses "(…)",
    et les montants avec séparateur de milliers espace.
    """
    match = re.match(
        r'''^
        ([A-Za-zÀ-ÿ\s\(\)\-\.'’]+?)             # poste : tout texte + espaces jusqu'au premier nombre (tolérance caractères spéciaux)
        \s+([-]|\(?\d{1,3}(?:\s\d{3})*\)?)\s*\$?   # montant 1 : nombre ou - ou (négatif) (+ $ facultatif)
        (?:\s+([-]|\(?\d{1,3}(?:\s\d{3})*\)?)\s*\$?)?   # montant 2 : nombre ou - ou (négatif) (+ $ facultatif, optionnel)
        $''', ligne, re.VERBOSE | re.UNICODE)
    if match:
        poste = match.group(1).strip()
        montant1 = match.group(2)
        montant2 = match.group(3) if match.group(3) else None

        def montant_to_int(m):
            if m is None:
                return None
            m = m.replace(" ", "")
            if m == "-":
                return 0
            if m.startswith("(") and m.endswith(")"):
                try:
                    return -int(m[1:-1])
                except ValueError:
                    return None
            try:
                return int(m)
            except ValueError:
                return None

        return {
            "poste": poste,
            "annee_courante": montant_to_int(montant1),
            "annee_precedente": montant_to_int(montant2)
        }
    return None

def process_pdf(file):
    """
    Traite un PDF donné en fichier ouvert (stream) et extrait les données financières ligne par ligne,
    renvoie une liste de dictionnaires avec poste et deux années.
    """
    results = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or len(text) < 40:
                # Fallback OCR si texte insuffisant
                page_image = page.to_image(resolution=300).original
                text = ocr_image(page_image)
            lines = text.split('\n')
            for ligne in lines:
                parsed = parse_ligne(ligne)
                if parsed and parsed['poste']:
                    results.append(parsed)
    return results
