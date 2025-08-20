import pdfplumber
import pytesseract
from PIL import Image
import re
from statistics import median

def ocr_image(image):
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception:
        return ""

def detect_col_positions(page, n_lignes=6, tol=2):
    lines = page.extract_text()
    if not lines:
        return None, None
    lines = lines.split("\n")
    line_chars = []
    for line in lines:
        tops = [c['top'] for c in page.chars if c['text'] and line.startswith(c['text'])]
        top = tops[0] if tops else None
        if top is not None:
            chars_in_line = [c for c in page.chars if abs(c['top'] - top) < tol]
            line_chars.append((line, chars_in_line))
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
                if table:
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

            if not debog_table_extract:
                # fallback : extraction ligne par ligne RAW + montants concaténés
                lignes = text.split("\n")
                for ligne in lignes:
                    if ligne.strip():
                        # Pas de parsing, simple extraction poste + chiffres concaténés
                        m = re.match(r'^([^\d]+)([\d\s\-\(\)\$]+)$', ligne.strip())
                        if m:
                            poste = m.group(1).strip()
                            montants = m.group(2).strip()
                            results.append({
                                "poste": poste,
                                "montants": montants,
                                "nom_poste_plus_long": nom_poste_plus_long,
                                "table_extract_roule": False
                            })

    return results
