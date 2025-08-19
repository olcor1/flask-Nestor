def extract_words_in_range(page, x_start, x_end):
    """Extrait le texte dans une plage de positions X."""
    words = []
    current_word = []
    prev_char = None

    for char in page.chars:
        if x_start <= char["x0"] <= x_end:
            # Regrouper les caractères en mots en fonction de leur proximité sur l'axe X
            if prev_char and abs(char["x0"] - prev_char["x1"]) < 5:  # Seuil de proximité pour les caractères d'un même mot
                current_word.append(char["text"])
            else:
                if current_word:
                    words.append("".join(current_word))
                    current_word = []
                current_word.append(char["text"])
            prev_char = char

    if current_word:
        words.append("".join(current_word))

    return " ".join(words).strip()

def parse_financial_page(page):
    """Parse une page financière en utilisant les positions X."""
    column_info = find_column_positions(page)
    data = {
        "sections": [],
        "postes": [],
        "totaux": [],
        "debug_info": {
            "longest_poste": column_info["longest_poste"],
            "first_col_end": column_info["first_col_end"],
            "dollar_positions": column_info["dollar_positions"],
            "second_col_end": column_info["second_col_end"]
        }
    }

    current_section = None
    words = page.chars
    lines = {}

    # Regroupe les caractères en lignes (par position Y)
    for char in words:
        y = round(char["top"], 1)
        if y not in lines:
            lines[y] = []
        lines[y].append(char)

    # Traite chaque ligne
    for y, chars_in_line in sorted(lines.items()):
        line_text = "".join([c["text"] for c in chars_in_line]).strip()
        if not line_text:
            continue

        # Détection des sections (lignes sans montants)
        if not re.search(r'\d', line_text):
            if any(section in line_text.upper() for section in ["PRODUITS", "CHARGES", "ACTIF", "PASSIF", "BÉNÉFICE"]):
                current_section = line_text
                data["sections"].append({
                    "nom": current_section,
                    "y_position": y
                })
            continue

        # Extrait les données en utilisant les positions X
        poste = extract_words_in_range(page, 0, column_info["first_col_end"])
        montant1 = extract_words_in_range(page, column_info["first_col_end"], column_info["second_col_end"])
        montant2 = extract_words_in_range(page, column_info["second_col_end"], page.width)

        montant1_clean = clean_montant(montant1)
        montant2_clean = clean_montant(montant2)

        if poste and (montant1_clean is not None or montant2_clean is not None):
            is_total = poste.upper().startswith(("BÉNÉFICE", "TOTAL", "SOMME"))

            data["postes"].append({
                "poste": poste,
                "montant1": montant1_clean,
                "montant2": montant2_clean,
                "est_total": is_total,
                "section": current_section,
                "y_position": y
            })

            if is_total:
                data["totaux"].append({
                    "poste": poste,
                    "montant1": montant1_clean,
                    "montant2": montant2_clean,
                    "section": current_section,
                    "y_position": y
                })

    return data

def process_pdf(file):
    """Traite le PDF en utilisant les coordonnées X pour les colonnes."""
    with pdfplumber.open(file) as pdf:
        full_text = ""
        result = {
            "metadata": {},
            "pages": [],
            "debug_info": {}
        }

        entreprise_id = generer_id_unique()

        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ocr_image(page.to_image().original)
            full_text += page_text + "\n"

            parsed_page = parse_financial_page(page)
            parsed_page["page_num"] = page_num + 1
            result["pages"].append(parsed_page)

            # Met à jour les infos de debug globales
            if "debug_info" in parsed_page:
                result["debug_info"].update(parsed_page["debug_info"])

        # Métadonnées
        first_page_text = pdf.pages[0].extract_text() or ocr_image(pdf.pages[0].to_image().original)
        doc = nlp(first_page_text)
        company_name = next((ent.text for ent in doc.ents if ent.label_ == "ORG"), "[ENTREPRISE]")

        ef_info = detecter_type_etats_financiers(first_page_text)
        annee_etats = detecter_annee_etats(first_page_text)
        date_complete = detecter_date_complete(first_page_text)

        result["metadata"] = {
            "entreprise_id": entreprise_id,
            "nom_entreprise_anonymise": company_name,
            "annee_etats_financiers": annee_etats,
            "date_etats_financiers": date_complete,
            "type_etats_financiers": ef_info["type"],
            "est_consolide": ef_info["consolide"],
            "date_extraction": datetime.now().strftime("%Y-%m-%d"),
            "source": file.filename
        }

        return result
