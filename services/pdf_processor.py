import fitz  # PyMuPDF
import re

def parse_montant(m):
    """Convertit une chaîne montant en int, gérant '-', parenthèses négatives, espaces"""
    if not m or m.strip() == "":
        return None
    m = m.replace(" ", "").replace("\xa0", "")
    if m in ["-", "–"]:
        return 0
    if m.startswith("(") and m.endswith(")"):
        try:
            return -int(m[1:-1])
        except:
            return None
    try:
        return int(m)
    except:
        return None

def process_pdf(file):
    """
    Ouvre un fichier pdf (chemin ou objet compatible fitz.open), extrait les lignes de tableau.
    """
    results = []
    doc = fitz.open(file)
    for page in doc:
        tables = page.find_tables()
        if not tables:
            # Fallback basique sur extraction texte ligne par ligne si pas de table détectée
            text = page.get_text("text")
            lines = text.split("\n")
            for ligne in lines:
                if not ligne.strip():
                    continue
                # Regex simple pour séparer poste et montants concaténés
                match = re.match(r'^([^\d]+)(.*)$', ligne.strip())
                if match:
                    poste = match.group(1).strip()
                    montants = match.group(2).strip()
                    results.append({
                        "poste": poste,
                        "montants": montants,
                        "annee_courante": None,
                        "annee_precedente": None
                    })
            continue

        # Pour chaque table détectée
        for tbl in tables:
            # tbl est une liste de rectangles (chaque rectangle = cellules de la table sur la page)
            # Extraction de texte par cellule via bbox
            rows_text = []
            for row in tbl:
                row_cells = []
                for cell_rect in row:
                    text = page.get_textbox(cell_rect).strip()
                    row_cells.append(text)
                rows_text.append(row_cells)

            for row in rows_text:
                if len(row) < 3:
                    continue
                poste = row[0]
                montant1 = parse_montant(row[1])
                montant2 = parse_montant(row)
                if poste:
                    results.append({
                        "poste": poste,
                        "annee_courante": montant1,
                        "annee_precedente": montant2
                    })
    return results
