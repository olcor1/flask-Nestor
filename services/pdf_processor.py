def detect_col_positions(pdf_page):
    lines = pdf_page.extract_text().split("\n")
    line_chars = []
    for line in lines:
        # Trouve les caractères de la ligne avec page.chars
        chars_in_line = [c for c in pdf_page.chars if abs(c['top'] - get_line_top(line, pdf_page.chars)) < 2]
        line_chars.append((line, chars_in_line))

    # Étape 1 : Trouve le poste le plus long
    poste_max = max(line_chars, key=lambda t: len(t[0].split()))
    poste_chars = [c for c in poste_max[1] if not c['text'].isdigit()]
    poste_fin_x = max([c['x1'] for c in poste_chars]) if poste_chars else None

    # Étape 4-5 : Pour quelques lignes avec montants, note le x1 du dernier chiffre de la première colonne montant
    positions_montant_1 = []
    for (ligne, chars) in line_chars[:5]:  # Prends les 5 premières lignes qui ressemblent à un poste+montant
        montant_chars = [c for c in chars if c['x0'] > poste_fin_x - 2 and c['text'].isdigit()]
        if montant_chars:
            montant1_fin_x = max([c['x1'] for c in montant_chars])
            positions_montant_1.append(montant1_fin_x)

    # Filtrer pour prendre la position la plus fréquente ou la moyenne des deux plus similaires
    if positions_montant_1:
        # Par exemple, prendre la médiane ou la première qui revient 2 fois
        from statistics import median
        montant1_fin_x = int(median(positions_montant_1))
    else:
        montant1_fin_x = poste_fin_x + 100  # fallback

    # positions = [poste_fin_x, montant1_fin_x] serviront à `extract_table`
    return [poste_fin_x, montant1_fin_x]

# Exemple d'appel :
with pdfplumber.open(file) as pdf:
    for page in pdf.pages:
        vertical_positions = detect_col_positions(page)
        table = page.extract_table(table_settings={
            "vertical_strategy": "explicit",
            "explicit_vertical_lines": vertical_positions
        })
