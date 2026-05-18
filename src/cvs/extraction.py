"""Extraction du texte brut d'un PDF via pdfplumber."""
import logging

import pdfplumber

logger = logging.getLogger(__name__)


def extraire_texte_pdf(chemin: str) -> str:
    """Retourne le texte brut concaténé de toutes les pages.

    Args:
        chemin: Chemin vers le fichier PDF.

    Returns:
        Texte brut, pages séparées par '\\n\\n--- Page X ---\\n\\n'.
        Chaîne vide si le PDF est illisible.
    """
    try:
        texte_total = []
        with pdfplumber.open(chemin) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text() or ""
                texte_total.append(f"--- Page {i} ---\n{t}")
        return "\n\n".join(texte_total)
    except Exception as e:
        logger.error("Erreur extraction PDF %s : %s", chemin, e)
        return ""
