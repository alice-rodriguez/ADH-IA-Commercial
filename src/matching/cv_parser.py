"""
Parseur de CVs — lit les fichiers PDF et DOCX et en extrait le texte.

Déposez vos CVs dans le dossier /cvs (PDF ou DOCX).
L'agent les indexe automatiquement au démarrage.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CVS_PATH = Path(os.getenv("CVS_PATH", "cvs/"))


def lire_pdf(chemin: Path) -> str:
    """Extrait le texte d'un PDF."""
    try:
        import pdfplumber
        texte = []
        with pdfplumber.open(chemin) as pdf:
            for page in pdf.pages:
                contenu = page.extract_text()
                if contenu:
                    texte.append(contenu)
        return "\n".join(texte)
    except ImportError:
        logger.error("pdfplumber non installé — pip install pdfplumber")
        return ""
    except Exception as e:
        logger.error("Erreur lecture PDF '%s' : %s", chemin.name, e)
        return ""


def lire_docx(chemin: Path) -> str:
    """Extrait le texte d'un fichier Word (.docx)."""
    try:
        from docx import Document
        doc = Document(chemin)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except ImportError:
        logger.error("python-docx non installé — pip install python-docx")
        return ""
    except Exception as e:
        logger.error("Erreur lecture DOCX '%s' : %s", chemin.name, e)
        return ""


def charger_tous_les_cvs() -> list[dict]:
    """
    Scanne le dossier cvs/ et retourne une liste de profils.
    Chaque profil = {'nom_fichier': ..., 'texte': ...}
    """
    CVS_PATH.mkdir(parents=True, exist_ok=True)
    profils = []

    fichiers = list(CVS_PATH.glob("*.pdf")) + list(CVS_PATH.glob("*.docx"))

    if not fichiers:
        logger.warning(
            "Aucun CV trouvé dans '%s'. Ajoutez des PDFs ou DOCX dans ce dossier.", CVS_PATH
        )
        return []

    for fichier in fichiers:
        suffix = fichier.suffix.lower()
        if suffix == ".pdf":
            texte = lire_pdf(fichier)
        elif suffix == ".docx":
            texte = lire_docx(fichier)
        else:
            continue

        if texte.strip():
            profils.append({
                "nom_fichier": fichier.name,
                "nom_candidat": fichier.stem.replace("_", " ").replace("-", " "),
                "texte": texte,
            })
            logger.info("CV chargé : %s (%d caractères)", fichier.name, len(texte))
        else:
            logger.warning("CV vide ou illisible : %s", fichier.name)

    logger.info("%d CV(s) chargé(s) depuis '%s'", len(profils), CVS_PATH)
    return profils
