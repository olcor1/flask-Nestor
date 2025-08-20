import fitz  # PyMuPDF

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

def process_pdf_with_find_tables(filepath):
    doc = fitz.open(filepath)
    results = []
    for page in doc:
        tables = page.find_tables()
        if not tables:
            continue
        for tbl in tables:
            # tbl is a list of rectangles representing cells, convert to text grid
            rows = []
            # Récupère les rectangles et fusionne par lignes avec tolérance
            blocks = page.get_text("blocks")
            # Utilise PyMuPDF helper pour extraire table textuelle
            for rect in tbl:
                # Chaque rect est un cell bbox : on extrait texte dans bbox
                cell_texts = []
                for r in rect:
                    cell_bbox = r
                    text = page.get_textbox(cell_bbox).strip()
                    cell_texts.append(text)
                rows.append(cell_texts)

            # Alternativement, utiliser page.extract_table avec bbox ciblé sur tbl
            # Mais pour simplicité, on parcourt les rows construits
            for row in rows:
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

# Exemple d'utilisation:
# file_path = "ton_etat_financier.pdf"
# data = process_pdf_with_find_tables(file_path)
# print(data)
