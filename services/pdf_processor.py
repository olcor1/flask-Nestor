def detect_col_positions(page, n_lignes=6, tol=2):
    text = page.extract_text()
    if not text:
        return "", [None, None]
    lines = text.split("\n")
    line_chars = []
    for line in lines:
        if not line or not isinstance(line, str):
            continue
        tops = [c['top'] for c in page.chars if c['text'] and line.startswith(c['text'])]
        top = tops if tops else None
        if top is not None:
            chars_in_line = [c for c in page.chars if abs(c['top'] - top) < tol]
            line_chars.append((line, chars_in_line))

    # Filtrer à nouveau si besoin
    line_chars = [(line, chars) for (line, chars) in line_chars if line and isinstance(line, str)]

    poste_max = max(line_chars, key=lambda t: len(re.sub(r'[\d\-\s$]+', '', t)), default=None)
    nom_poste_plus_long = poste_max.strip() if poste_max else ""
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
