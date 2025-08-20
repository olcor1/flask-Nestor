import pdfplumber
import pytesseract
from PIL import Image
import re
from statistics import median

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception:
        return ""

def get_line_top(target_line, chars):
    """
    Retourne la coordonnée 'top' la plus probable pour une ligne donnée.
    Sécurise en vérifiant les types et que la chaîne n’est pas vide.
    """
    if not isinstance(target_line, str) or not target_line.strip():
        return None
    for c in chars:
        if not c['text'] or not isinstance(c['text'], str):
            continue
        if target_line.startswith(c['text']):
            return c['top']
    return None

def detect_col_positions(page, n_lignes=6, tol=2):
    text = page.extract_text()
    if not text:
        return "", [None, None]
    lines = text.split("\n")
    line_chars = []
    for line in lines:
        if not line or not isinstance(line, str) or line.strip() == "":
            continue
        top = get_line_top(line, page.chars)
        if top is not None:
            chars_in_line = [c for c in page.chars if abs(c['top'] - top) < tol]
            line_chars.append((line, chars_in_line))

    line_chars = [(line, chars) for (line, chars) in line_chars if line and isinstance(line, str) and line.strip() != '']
    if not line_chars:
        return "", [None, None]

    poste_max = max(line_chars, key=lambda t: len(re.sub(r'[\d\-\s$]+', '', t[0])), default=None)
    nom_poste_plus_long = poste_max[0].strip() if poste_max else ""
    if poste_max:
        poste_chars = [c for c in poste_max[1] if not c['text'].isdigit()]
        poste_fin_x = max([c['x1'] for c in poste_chars]) if poste_chars else 0
    else:
        poste_fin_x = 0

    montant1_fins = []
    for (ligne, chars) in line_chars[:n_lignes]:
        montant_chars = [c for c in chars if c['x0'] > poste_fin_x - 2 and (c['text'].isdigit() or c['text'] in "-()")]
        if not montant_chars:
            continue
        montant1_part = []
        prev_is_digit = False
        for c in montant_chars:
            if c['text'].isdigit() or c['text'] in "()-":
                montant1_part.append(c)
                prev_is_digit = True
            elif prev_is_digit:
                break
        if montant1_part:
            montant1_fin_x = max([c['x1'] for c in montant1_part])
            montant1_fins.append(montant1_fin_x)
    montant1_fin_x = int(median(montant1_fins)) if montant1_fins else poste_fin_x + 85

    return nom_poste_plus_long, [int(poste_fin_x), montant1_fin_x]

def process_pdf(file):
    results = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or len(text.strip()) < 40:
                page_image = page.to_image(resolution=300).original
                text = ocr_image(page_image)
                if not text or len(text.strip()) < 40:
                    continue
            nom_poste_plus_long, positions = detect_col_positions(page)

            debog_table_extract = False
            if positions and positions[0] is not None and positions[1] is not None:
                table = page.extract_table(table_settings={
                    "vertical_strategy": "explicit",
                    "explicit_vertical_lines": positions
                })
                if table and len(table) > 0:
                    debog_table_extract = True
                    for row in table:
                        if row and len(row) >= 2 and row[0]:
                            poste = row[0].strip()
                            montants = " ".join(filter(None, [cell.strip() if cell else "" for cell in row[1:]]))
                            results.append({
                                "poste": poste,
                                "montants": montants,
                                "nom_poste_plus_long": nom_poste_plus_long,
                                "table_extract_roule": True
                            })

            # Fallback sur toutes les lignes sinon
            if not debog_table_extract:
                for ligne in text.split("\n"):
                    if not ligne.strip():
                        continue
                    match = re.match(r'^([^\d]+)(.*)$', ligne.strip())
                    if match:
                        poste = match.group(1).strip()
                        montants = match.group(2).strip()
                        results.append({
                            "poste": poste,
                            "montants": montants,
                            "nom_poste_plus_long": nom_poste_plus_long,
                            "table_extract_roule": False
                        })
    return results
