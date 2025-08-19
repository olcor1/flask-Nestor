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

def is_poste_char(c):
    """Détermine si un caractère fait partie du poste (lettres, chiffres, espaces, parenthèses)."""
    return c['text'].isalnum() or c['text'] in [' ', '(', ')']

def detect_column_positions(page):
    chars = page.chars
    postes_chars = [c for c in chars if is_poste_char(c)]
    montant_chars = [c for c in chars if c['text'].isdigit()]
    poste_fin_x = max(c['x1'] for c in postes_chars) if postes_chars else 0
    montant_apres_poste = [c for c in montant_chars if c['x0'] > poste_fin_x]
    colonne_2_fin_x = max(c['x1'] for c in montant_apres_poste) if montant_apres_poste else poste_fin_x + 100
    return poste_fin_x, colonne_2_fin_x

def extract_text_by_bbox(page, bbox):
    chars = [c for c in page.chars if 
             c['x0'] >= bbox[0] and c['x1'] <= bbox[2] and 
             c['top'] >= bbox[1] and c['bottom'] <= bbox[3]]

    lines = []
    line_tolerance = 3
    chars = sorted(chars, key=lambda c: (c['top'], c['x0']))
    current_line = []
    current_top = None

    for c in chars:
        if current_top is None or abs(c['top'] - current_top) <= line_tolerance:
            current_line.append(c)
            if current_top is None:
                current_top = c['top']
        else:
            lines.append(current_line)
            current_line = [c]
            current_top = c['top']
    if current_line:
        lines.append(current_line)

    lines_text = []
    for line_chars in lines:
        line_text = "".join(c['text'] for c in sorted(line_chars, key=lambda c: c['x0']))
        lines_text.append(line_text.strip())
    return lines_text

def merge_columns(postes, col2, col3):
    result = []
    max_lines = max(len(postes), len(col2), len(col3))
    for i in range(max_lines):
        poste = postes[i] if i < len(postes) else ""
        c2 = col2[i] if i < len(col2) else ""
        c3 = col3[i] if i < len(col3) else ""
        
        def clean_montant(m):
            m_clean = m.replace(" ", "")
            return int(m_clean) if m_clean.isdigit() else None
        
        annee_courante = clean_montant(c2)
        annee_precedente = clean_montant(c3)
        
        if poste:
            result.append({
                "poste": poste,
                "annee_courante": annee_courante,
                "annee_precedente": annee_precedente
            })
    return result

def process_pdf(file):
    """Traite le PDF envoyé en fichier (stream) en utilisant pdfplumber et la découpe par position des colonnes."""
    results = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or len(text) < 40:
                page_image = page.to_image(resolution=300).original
                text = ocr_image(page_image)
            poste_fin_x, col2_fin_x = detect_column_positions(page)
            bbox_poste = (0, 0, poste_fin_x, page.height)
            bbox_col2 = (poste_fin_x + 1, 0, col2_fin_x, page.height)
            bbox_col3 = (col2_fin_x + 1, 0, page.width, page.height)

            postes = extract_text_by_bbox(page, bbox_poste)
            col2 = extract_text_by_bbox(page, bbox_col2)
            col3 = extract_text_by_bbox(page, bbox_col3)

            page_results = merge_columns(postes, col2, col3)
            results.extend(page_results)

    return results
