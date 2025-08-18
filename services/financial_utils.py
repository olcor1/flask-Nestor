import re
from typing import Dict, Optional
from datetime import datetime

def detecter_section(poste: str, etat: str) -> Optional[str]:
    poste_lower = poste.lower()
    if etat == "bilan":
        if any(kw in poste_lower for kw in ["courant", "court terme"]):
            return "Actif court terme"
        elif any(kw in poste_lower for kw in ["immobilisé", "long terme"]):
            return "Actif long terme"
    return None

def extraire_montants_annees(line: str) -> Dict[str, Optional[float]]:
    parts = re.split(r'\s{2,}', line.strip())
    montant_courant = None
    montant_precedent = None
    if len(parts) >= 3:
        try:
            montant_courant = float(parts[-1].replace(' ', '').replace(',', '.'))
            montant_precedent = float(parts[-2].replace(' ', '').replace(',', '.'))
        except:
            pass
    elif len(parts) >= 2:
        try:
            montant_courant = float(parts[-1].replace(' ', '').replace(',', '.'))
        except:
            pass
    return {"courant": montant_courant, "precedent": montant_precedent}

def detecter_reference_annexe(text: str) -> Optional[str]:
    match = re.search(r'\(?voir annexe ([A-Za-z0-9])\)?', text.lower())
    return match.group(1) if match else None

def detecter_type_etats_financiers(text: str) -> Dict[str, Optional[str]]:
    text_lower = text.lower()
    type_ef = None
    if "audité" in text_lower:
        type_ef = "audité"
    elif "mission d'examen" in text_lower:
        type_ef = "mission d'examen"
    elif "compilé" in text_lower:
        type_ef = "compilé"
    est_consolide = "consolidé" in text_lower
    return {"type": type_ef, "consolide": est_consolide if est_consolide else None}

def detecter_annee_etats(text: str) -> int:
    match = re.search(r'(?:exercice|année|clos le).*?(\d{4})', text.lower())
    return int(match.group(1)) if match else datetime.now().year
