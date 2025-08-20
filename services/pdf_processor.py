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

def parse_ligne_regex_advanced(ligne):
    """
    Parse une ligne en gérant les montants collés.
    Exemple: "Frais bancaires 3300799" -> "Frais bancaires", 3300, 799
    """
    # D'abord, essayer le pattern normal (montants séparés)
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
    
    # Si ça n'a pas marché, essayer avec montants collés
    match_colle = re.match(r'^([A-Za-zÀ-ÿ\s\(\)\-\.'']+?)\s+(\d+)\s*\$?\s*$', ligne)
    if match_colle:
        poste = match_colle.group(1).strip()
        montants_colles = match_colle.group(2)
        
        # Essayer de séparer les montants collés
        montant1, montant2 = separer_montants_colles(montants_colles)
        
        return {
            "poste": poste,
            "annee_courante": montant1,
            "annee_precedente": montant2
        }
    
    return None

def separer_montants_colles(montants_str):
    """
    Essaie de séparer une chaîne de chiffres collés en deux montants.
    Utilise des heuristiques basées sur la longueur et les patterns typiques.
    """
    if len(montants_str) <= 3:
        # Trop court pour être deux montants
        return int(montants_str), None
    
    # Stratégies de découpage par longueur
    strategies = [
        # Derniers 3 chiffres comme 2e montant
        (montants_str[:-3], montants_str[-3:]),
        # Derniers 4 chiffres comme 2e montant  
        (montants_str[:-4], montants_str[-4:]) if len(montants_str) > 4 else None,
        # Derniers 5 chiffres comme 2e montant
        (montants_str[:-5], montants_str[-5:]) if len(montants_str) > 5 else None,
        # Derniers 6 chiffres comme 2e montant
        (montants_str[:-6], montants_str[-6:]) if len(montants_str) > 6 else None,
        # Milieu approximatif
        (montants_str[:len(montants_str)//2], montants_str[len(montants_str)//2:]) if len(montants_str) > 6 else None
    ]
    
    # Filtrer les stratégies nulles
    strategies = [s for s in strategies if s is not None]
    
    # Choisir la stratégie qui donne des montants les plus "raisonnables"
    # (éviter des montants de 1 ou 2 chiffres sauf
