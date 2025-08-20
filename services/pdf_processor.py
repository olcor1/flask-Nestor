import pdfplumber
import pytesseract
from PIL import Image
import spacy
import re
from statistics import median

nlp = spacy.load("fr_core_news_md")

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception:
        return ""

def get_line_top(target_line, chars):
    """
    Retourne la coordonnée 'top' la plus probable pour une ligne donnée d'après les caractères de pdfplumber.
    """
    for c in chars:
        # Recherche le premier caractère qui appartient à la ligne
        if c['text'] and c['text'][0] in target_line:
            return c['top']
    return None

def detect_col_positions(page, n_lignes=6, tol=2):
    """
    Détecte les positions verticales (x) pour découper le tableau :
    - Fin du poste le plus long (Position A)
    - Fin du montant 1 le plus 'concordant' (Position B)
    """
    lines = page.extract_text().split("\n")
    line_chars = []
    for line in lines:
        top = get_line_top(line, page.chars)
        if top is not None:
            chars_in_line = [c for c in page.chars if abs(c['top'] - top) < tol]
            line_chars.append((line, chars_in_line))
    # Poste le plus long
    poste_max = max(line_chars, key=lambda t: len(re.sub(r'[\d\-\s$]+', '', t[0])), default=None)
    if poste_max:
        poste_chars = [c for c in poste_max[1] if not c['text'].isdigit()]
        poste_fin_x = max([c['x1'] for c in poste_chars]) if poste_chars else 0
    else:
        poste_fin_x = 0

    # Fin du montant 1 sur les premières lignes détectées
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

    return [int(poste_fin_x), montant1_fin_x]

def parse_extracted_table(extracted_table):
    """
    Prend une table extraite par pdfplumber et la formate proprement.
    """
    results = []
    for row in extracted_table:
        if not row or len(row) < 2:
            continue
        poste = row[0].strip() if row[0] else ""
        montant1 = row[1].replace(" ", "").replace('\xa0','') if len(row) > 1 and row[1] else None
        montant2 = row[2].replace(" ", "").replace('\xa0','') if len(row) > 2 and row[2] else None
        def montant_to_int(m):
            if not m or m == "":
                return None
            if m in ["-", "–"]:
                return 0
            if m.startswith("(") and m.endswith(")"):
                try:
                    return -int(m[1:-1])
                except Exception:
                    return None
            try:
                return int(m)
            except Exception:
                return None
        results.append({
            "poste": poste,
            "annee_courante": montant_to_int(montant1),
            "annee_precedente": montant_to_int(montant2)
        })
    return results

def process_pdf(file):
    """
    Extraction robuste avec positions dynamiques sur pdf natif.
    Utilise une détection automatique des colonnes selon le poste le plus long et la fin du montant 1.
    """
    results = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or len(text.strip()) < 40:
                page_image = page.to_image(resolution=300).original
                text = ocr_image(page_image)
                raise ValueError("Extraction OCR non implémentée dans ce script.")
            verticals = detect_col_positions(page)
            table = page.extract_table(table_settings={
                "vertical_strategy": "explicit",
                "explicit_vertical_lines": verticals
            })
            if table:
                results += parse_extracted_table(table)
    return results
