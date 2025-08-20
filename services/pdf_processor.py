import fitz  # PyMuPDF
import re
import tempfile

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

def process_pdf(uploaded_file):
    """
    Processus pour lire un fichier uploadé via Flask (FileStorage),
    sauvegarder temporairement, puis extraire les données financières
    par PyMuPDF.
    """
    results = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        uploaded_file.save(tmp.name)
        doc = fitz.open(tmp.name)
        for page in doc:
            tables = page.find_tables()
            if not tables:
                # Fallback basique sur extraction texte ligne par ligne
                text = page.get_text("text")
                lines = text.split("\n")
                for ligne in lines:
                    if not ligne.strip():
                        continue
                    match = re.match(r'^([^\d]+)(.*)$', ligne.strip())
                    if match:
                        poste = match.group(1).strip()
                        montants = match.group(2).strip()
                        results.append({
                            "poste": poste,
                            "montants_raw": montants,
                            "annee_courante": None,
                            "annee_precedente": None
                        })
                continue

            # Extraction par table trouvée
            for tbl in tables:
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
                    montant2 = parse_montant(row[2])
                    if poste:
                        results.append({
                            "poste": poste,
                            "annee_courante": montant1,
                            "annee_precedente": montant2
                        })
    return results
