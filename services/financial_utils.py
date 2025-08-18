import re
from typing import Dict, Optional
from datetime import datetime

def detecter_section_pdf(text: str) -> str:
    """Détecte la section actuelle (Produits, Charges, etc.)."""
    text_upper = text.upper()
    if "PRODUITS" in text_upper:
        return "Produits"
    elif "CHARGES LOCATIVES" in text_upper:
        return "Charges locatives"
    elif "BÉNÉFICE" in text_upper:
        return "Bénéfice"
    return "Autre"

def detecter_date_complete(text: str) -> Optional[str]:
    """Extrait la date complète (ex: '30 septembre 2020')."""
    match = re.search(r'(?:au|le|terminé le)\s*(\d{1,2}\s*\w+\s*\d{4})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'(\d{1,2}\s*\w+\s*\d{4})', text)  # Format libre
    return match.group(1) if match else None

def detecter_annee_etats(text: str) -> int:
    """Détecte l'année des états financiers."""
    match = re.search(r'(\d{4})', text)
    return int(match.group(1)) if match else datetime.now().year

def detecter_type_etats_financiers(text: str) -> Dict[str, Optional[str]]:
    """Détecte le type d'états financiers et si consolidé."""
    text_lower = text.lower()
    type_ef = None
    if "audité" in text_lower:
        type_ef = "audité"
    elif "mission d'examen" in text_lower:
        type_ef = "mission d'examen"
    elif "compilé" in text_lower:
        type_ef = "compilé"

    est_consolide = "consolidé" in text_lower and "non consolidé" not in text_lower
    return {"type": type_ef, "consolide": est_consolide if "consolidé" in text_lower else None}
