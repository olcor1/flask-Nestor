import pdfplumber
import re

def find_column_positions(page):
    """Trouve les positions X des colonnes en analysant les caractères."""
    words = page.chars  # Tous les caractères avec leurs positions X/Y

    # Trouve la position X maximale des mots de la 1ère colonne (sans chiffres)
    max_x_first_col = 0
    longest_poste = {"text": "", "x_end": 0}

    # Trouve les positions X des "$" pour les colonnes de montants
    dollar_positions = []

    # Regrouper les caractères en mots
    words_in_page = []
    current_word = []
    prev_char = None

    for char in sorted(words, key=lambda c: (c["top"], c["x0"])):
        if prev_char and abs(char["x0"] - prev_char["x1"]) < 5:  # Seuil de proximité pour les caractères d'un même mot
            current_word.append(char)
        else:
            if current_word:
                words_in_page.append(current_word)
                current_word = []
            current_word.append(char)
        prev_char = char

    if current_word:
        words_in_page.append(current_word)

    # Parcourir les mots pour trouver le plus long et les positions des "$"
    for word_chars in words_in_page:
        word_text = "".join([c["text"] for c in word_chars]).strip()
        word_x_end = max(c["x1"] for c in word_chars)

        if not any(c.isdigit() for c in word_text):  # Ignore les mots avec des chiffres (montants)
            if word_x_end > max_x_first_col and len(word_text) > len(longest_poste["text"]):
                max_x_first_col = word_x_end
                longest_poste = {"text": word_text, "x_end": word_x_end}

        if "$" in word_text:
            for char in word_chars:
                if char["text"] == "$":
                    dollar_positions.append(char["x0"])

    # Détermine les positions X des colonnes
    first_col_end = max_x_first_col if max_x_first_col > 0 else 200  # Valeur par défaut
    second_col_end = min(dollar_positions) if dollar_positions else first_col_end + 100

    return {
        "first_col_end": first_col_end,
        "second_col_end": second_col_end
    }

def parse_financial_page(page):
    """Parse une page financière en utilisant les positions X."""
    # Obtenir les positions des colonnes pour cette page
    column_info = find_column_positions(page)
    first_col_end = column_info["first_col_end"]
    second_col_end = column_info["second_col_end"]

    # Définir les colonnes explicitement
    table_settings = {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "text",
        "explicit_vertical_lines": [0, first_col_end, second_col_end, page.width]
    }

    # Extraire le tableau avec les colonnes définies
    try:
        table = page.extract_table(table_settings)
        return table
    except Exception as e:
        print(f"Failed to extract table: {e}")
        return None

def process_pdf(file_path):
    """Traite le PDF en utilisant les coordonnées X pour les colonnes."""
    try:
        with pdfplumber.open(file_path) as pdf:
            # Traiter uniquement la page 2
            if len(pdf.pages) >= 2:
                page = pdf.pages[1]  # Index 1 correspond à la page 2 (index 0 est la page 1)
                result = parse_financial_page(page)
                return result
            else:
                return {"status": "error", "message": "PDF does not have a second page"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

    print(result)
except Exception as e:
    print({"status": "error", "message": str(e)})
