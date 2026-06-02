"""Génération du PDF CV adapté ADH (WeasyPrint + Jinja2 + Haiku)."""
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from api.database import get_cv_par_id, get_offre_par_id
from src.cv_genere.reformulation import reformuler_avec_haiku
from src.storage.database import _connexion

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
ASSETS_DIR = TEMPLATES_DIR / "assets"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "cvs_generes"


def _get_version_suivante(cv_id: int, offre_id: int) -> int:
    with _connexion() as conn:
        row = conn.execute(
            "SELECT MAX(version) FROM cvs_generes WHERE cv_id = ? AND offre_id = ?",
            (cv_id, offre_id),
        ).fetchone()
    current = row[0] if row and row[0] is not None else 0
    return current + 1


def _enregistrer_en_bdd(cv_id: int, offre_id: int, version: int,
                         chemin: str, contact_email: str, contact_telephone: str) -> None:
    with _connexion() as conn:
        conn.execute(
            """INSERT INTO cvs_generes
               (cv_id, offre_id, version, chemin_fichier, contact_email, contact_telephone)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cv_id, offre_id, version, chemin, contact_email, contact_telephone),
        )


def generer_pdf(cv_id: int, offre_id: int,
                contact_email: str, contact_telephone: str) -> str:
    """Génère un PDF CV adapté ADH et retourne son chemin absolu.

    Raises:
        RuntimeError si données manquantes ou génération échoue.
    """
    cv = get_cv_par_id(cv_id)
    if cv is None:
        raise RuntimeError(f"CV {cv_id} introuvable en BDD.")

    offre = get_offre_par_id(offre_id)
    if offre is None:
        raise RuntimeError(f"Offre {offre_id} introuvable en BDD.")

    if not cv.get("titre_courant"):
        raise RuntimeError(
            f"Le CV {cv_id} n'a pas de titre_courant — profilage requis avant génération."
        )

    # Reformulation par Haiku
    contenu = reformuler_avec_haiku(cv, offre)

    # Calcul ID consultant
    id_consultant = f"IDADH-{cv_id:03d}"

    # Chemins images (file:// pour WeasyPrint)
    picto_path = ASSETS_DIR / "picto-adh.png"
    logo_path = ASSETS_DIR / "logo-adh.png"

    # Rendu Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("cv_adh.html")

    html_str = template.render(
        id_consultant=id_consultant,
        titre_consultant=cv.get("titre_courant", "Consultant IT"),
        annees_experience=cv.get("annees_experience"),
        offre_titre=offre.get("titre", ""),
        offre_entreprise=offre.get("entreprise") or "",
        offre_lieu=offre.get("lieu") or "",
        offre_contrat=offre.get("type_contrat_clarifie") or offre.get("type_contrat") or "",
        contact_email=contact_email,
        contact_telephone=contact_telephone,
        competences_top6=contenu.get("competences_top6") or [],
        formations=contenu.get("formations") or [],
        certifications=contenu.get("certifications") or [],
        secteurs=contenu.get("secteurs") or "",
        langues=contenu.get("langues") or [],
        profil_reformule=contenu.get("profil_reformule") or "",
        experiences=contenu.get("experiences") or [],
        picto_path=picto_path.as_uri(),
        logo_path=logo_path.as_uri(),
    )

    # Génération PDF
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()

    # Chemin de sortie
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    version = _get_version_suivante(cv_id, offre_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_fichier = f"{cv_id}_{offre_id}_v{version}_{ts}.pdf"
    chemin = OUTPUT_DIR / nom_fichier

    chemin.write_bytes(pdf_bytes)
    logger.info("PDF généré : %s", chemin)

    _enregistrer_en_bdd(cv_id, offre_id, version, str(chemin), contact_email, contact_telephone)

    return str(chemin)
