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

def parse_ligne_regex(ligne):
    """
    Fallback : parse une ligne avec regex comme avant, mais amélioré.
    """
    # Regex pour capturer : poste + 1 ou 2 montants (avec gestion "-" et parenthèses)
    match = re.match(
        r'^([A-Za-zÀ-ÿ\s\(\)\-\.'']+?)\s+([-]|\(?\d{1,3}(?:\s\d{3})*\)?)\s*\$?\s*(?:\s+([-]|\(?\d{1,3}(?:\s\d{3})*\)?)\s*\$?)?\s*$',
        ligne
    )
    if match:
        poste = match.group(1).strip()
        montant1 = match.group(2)
        montant2 = match.group(3) if match.group(3) else None

        def montant_to_int(m):
            if not m or m == "":
                return None
            m = m.replace(" ", "")
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

        return {
            "poste": poste,
            "annee_courante": montant_to_int(montant1),
            "annee_precedente": montant_to_int(montant2)
        }
    return None

def detect_col_positions(page):
    """Version simplifiée de détection des positions."""
    try:
        chars = page.chars
        if not chars:
            return None
            
        # Trouve la position x max des caractères non-numériques (fin des postes)
        non_digit_chars = [c for c in chars if not c['text'].isdigit() and c['text'] not in '$-()']
        if non_digit_chars:
            poste_fin_x = max([c['x1'] for c in non_digit_chars])
        else:
            return None
            
        # Trouve la position x max des premiers montants
        digit_chars = [c for c in chars if c['text'].isdigit() and c['x0'] > poste_fin_x]
        if digit_chars:
            # Groupe les chiffres par ligne approximative et prend le milieu
            lines_digits = {}
            for c in digit_chars:
                line_key = round(c['top'] / 5) * 5  # Groupe par tranches de 5px
                if line_key not in lines_digits:
                    lines_digits[line_key] = []
                lines_digits[line_key].append(c)
            
            montant1_fins = []
            for line_digits in lines_digits.values():
                if len(line_digits) > 2:  # Si plusieurs chiffres sur la ligne
                    # Prend le milieu approximatif comme fin de colonne 1
                    sorted_digits = sorted(line_digits, key=lambda c: c['x0'])
                    mid_index = len(sorted_digits) // 2
                    montant1_fin_x = sorted_digits[mid_index]['x1']
                    montant1_fins.append(montant1_fin_x)
            
            if montant1_fins:
                montant1_fin_x = int(median(montant1_fins))
                return [int(poste_fin_x), montant1_fin_x]
                
        return None
    except Exception:
        return None

def process_pdf(file):
    """
    Version hybride : essaie d'abord l'extraction de table, puis fallback regex.
    """
    results = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or len(text.strip()) < 40:
                page_image = page.to_image(resolution=300).original
                text = ocr_image(page_image)
                if not text or len(text.strip()) < 40:
                    continue
            
            # Essaie d'abord la méthode de détection de positions
            table_extracted = False
            try:
                positions = detect_col_positions(page)
                if positions:
                    table = page.extract_table(table_settings={
                        "vertical_strategy": "explicit",
                        "explicit_vertical_lines": positions
                    })
                    if table and len(table) > 0:
                        for row in table:
                            if row and len(row) >= 2 and row[0] and row.strip():
                                poste = row.strip()
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
                        table_extracted = True
            except Exception:
                pass
            
            # Fallback : méthode regex ligne par ligne
            if not table_extracted:
                lines = text.split('\n')
                for ligne in lines:
                    parsed = parse_ligne_regex(ligne)
                    if parsed and parsed['poste']:
                        results.append(parsed)
    
    return results
