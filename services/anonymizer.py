import re
import spacy

nlp = spacy.load("fr_core_news_md")

def anonymize_text(text: str, company_name: str) -> str:
    text = text.replace(company_name, "[ENTREPRISE]")
    text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', "[EMAIL]", text)
    text = re.sub(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', "[TEL]", text)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            text = text.replace(ent.text, "[NOM]")
    return text
