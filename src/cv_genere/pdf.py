"""Génération du PDF CV adapté ADH (WeasyPrint + Jinja2 + Haiku)."""
import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from api.database import get_cv_par_id, get_offre_par_id
from src.cv_genere.langue import detecter_langue_cv, get_labels
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

    # Détection de la langue du CV brut
    langue = detecter_langue_cv(cv.get("texte_brut") or "")
    labels = get_labels(langue)

    # Reformulation par Haiku dans la langue détectée
    contenu = reformuler_avec_haiku(cv, offre, langue=langue)

    # Cascade profil : Notes ADH > Haiku
    profil_final = (cv.get("profil_adh") or "").strip()
    if not profil_final:
        profil_final = (contenu.get("profil") or "").strip()

    # Titre KEY VALUE (calculé en Python, pas par Haiku)
    entreprise = (offre.get("entreprise") or "").strip()
    if entreprise:
        if langue == "fr":
            titre_key_value = f"POINTS FORTS POUR {entreprise.upper()}"
        else:
            titre_key_value = f"KEY VALUE FOR {entreprise.upper()}"
    else:
        titre_key_value = "POINTS FORTS" if langue == "fr" else "KEY VALUE PROPOSITION"

    # Secteurs dérivés des domaines du CV (pas via Haiku)
    domaines_cv = cv.get("domaines") or []
    if isinstance(domaines_cv, str):
        try:
            domaines_cv = json.loads(domaines_cv)
        except (json.JSONDecodeError, TypeError):
            domaines_cv = []
    secteurs = " · ".join(domaines_cv[:5]) if domaines_cv else ""

    # Label "X ans d'expérience" formaté
    annees_experience = cv.get("annees_experience")
    annees_exp_label = None
    if annees_experience is not None:
        annees_exp_label = labels["annees_experience"].replace("{n}", str(annees_experience))

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
        annees_exp_label=annees_exp_label,
        offre_titre=offre.get("titre", ""),
        offre_entreprise=offre.get("entreprise") or "",
        offre_lieu=offre.get("lieu") or "",
        offre_contrat=offre.get("type_contrat_clarifie") or offre.get("type_contrat") or "",
        contact_email=contact_email,
        contact_telephone=contact_telephone,
        competences_top6=contenu.get("competences_top6_ordonnees") or [],
        formations=contenu.get("formations") or [],
        certifications=contenu.get("certifications") or [],
        secteurs=secteurs,
        langues=contenu.get("langues") or [],
        profil_final=profil_final,
        key_value_bullets=contenu.get("key_value_bullets") or [],
        titre_key_value=titre_key_value,
        experiences=contenu.get("experiences") or [],
        picto_path=picto_path.as_uri(),
        logo_path=logo_path.as_uri(),
        labels=labels,
        langue=langue,
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
