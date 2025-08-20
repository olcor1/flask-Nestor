import pdfplumber
import pytesseract
from PIL import Image
import spacy
import re

nlp = spacy.load("fr_core_news_md")

def ocr_image(image):
    """Effectue l'OCR sur une image avec gestion des erreurs."""
    try:
        return pytesseract.image_to_string(image, lang='fra+eng')
    except Exception:
        return ""

def parse_ligne_simple(ligne):
    """Parse une ligne avec gestion basique des montants collés."""
    try:
        # Essaie d'abord le pattern normal
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
                    except:
                        return None
                try:
                    return int(m)
                except:
                    return None

            return {
                "poste": poste,
                "annee_courante": montant_to_int(montant1),
                "annee_precedente": montant_to_int(montant2)
            }
        
        # Si pas de match normal, essaie montants collés
        match_colle = re.match(r'^([A-Za-zÀ-ÿ\s\(\)\-\.'']+?)\s+(\d{5,})\s*$', ligne)
        if match_colle:
            poste = match_colle.group(1).strip()
            montants_str = match_colle.group(2)
            
            # Simple : coupe au milieu pour les nombres longs
            if len(montants_str) >= 6:
                milieu = len(montants_str) // 2
                montant1 = int(montants_str[:milieu])
                montant2 = int(montants_str[milieu:])
            else:
                montant1 = int(montants_str)
                montant2 = None
            
            return {
                "poste": poste,
                "annee_courante": montant1,
                "annee_precedente": montant2
            }
            
    except Exception:
        pass
    
    return None

def process_pdf(file):
    """Version simple et robuste."""
    results = []
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                try:
                    text = page.extract_text()
                    if not text or len(text.strip()) < 40:
                        page_image = page.to_image(resolution=300).original
                        text = ocr_image(page_image)
                        if not text or len(text.strip()) < 40:
                            continue
                    
                    lines = text.split('\n')
                    for ligne in lines:
                        if ligne.strip():
                            parsed = parse_ligne_simple(ligne.strip())
                            if parsed and parsed['poste']:
                                results.append(parsed)
                                
                except Exception as e:
                    continue
                    
    except Exception as e:
        return []
    
    return results
