"""Génération du PDF CV adapté ADH (WeasyPrint + Jinja2 + Haiku)."""
import json
import logging
import shutil
import uuid
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
DRAFTS_DIR = Path(__file__).resolve().parent.parent.parent / "cvs_generes_drafts"


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


def _generer_pdf_interne(
    cv_id: int,
    offre_id: int,
    contact_email: str,
    contact_telephone: str,
    langue_forcee: str | None = None,
    titre_key_value_custom: str | None = None,
    instructions_supplementaires: str = "",
) -> tuple[bytes, str, str]:
    """Génère les bytes du PDF et retourne (pdf_bytes, langue_effective, titre_key_value_effectif).

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

    langue = langue_forcee or detecter_langue_cv(cv.get("texte_brut") or "")
    labels = get_labels(langue)

    contenu = reformuler_avec_haiku(
        cv, offre, langue=langue,
        instructions_supplementaires=instructions_supplementaires,
    )

    profil_final = (cv.get("profil_adh") or "").strip()
    if not profil_final:
        profil_final = (contenu.get("profil") or "").strip()

    entreprise = (offre.get("entreprise") or "").strip()
    if titre_key_value_custom and titre_key_value_custom.strip():
        titre_key_value = titre_key_value_custom.strip()
    elif entreprise:
        if langue == "fr":
            titre_key_value = f"POINTS FORTS POUR {entreprise.upper()}"
        else:
            titre_key_value = f"KEY VALUE FOR {entreprise.upper()}"
    else:
        titre_key_value = "POINTS FORTS" if langue == "fr" else "KEY VALUE PROPOSITION"

    domaines_cv = cv.get("domaines") or []
    if isinstance(domaines_cv, str):
        try:
            domaines_cv = json.loads(domaines_cv)
        except (json.JSONDecodeError, TypeError):
            domaines_cv = []
    secteurs = " · ".join(domaines_cv[:5]) if domaines_cv else ""

    annees_experience = cv.get("annees_experience")
    annees_exp_label = None
    if annees_experience is not None:
        annees_exp_label = labels["annees_experience"].replace("{n}", str(annees_experience))

    id_consultant = f"IDADH-{cv_id:03d}"
    picto_path = ASSETS_DIR / "picto-adh.png"
    logo_path = ASSETS_DIR / "logo-adh.png"

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

    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
    return pdf_bytes, langue, titre_key_value


def generer_pdf(cv_id: int, offre_id: int,
                contact_email: str, contact_telephone: str) -> str:
    """Génère un PDF CV adapté ADH et retourne son chemin absolu.

    Raises:
        RuntimeError si données manquantes ou génération échoue.
    """
    pdf_bytes, _, _ = _generer_pdf_interne(cv_id, offre_id, contact_email, contact_telephone)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    version = _get_version_suivante(cv_id, offre_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_fichier = f"{cv_id}_{offre_id}_v{version}_{ts}.pdf"
    chemin = OUTPUT_DIR / nom_fichier
    chemin.write_bytes(pdf_bytes)
    logger.info("PDF généré : %s", chemin)
    _enregistrer_en_bdd(cv_id, offre_id, version, str(chemin), contact_email, contact_telephone)
    return str(chemin)


def generer_pdf_draft(
    cv_id: int,
    offre_id: int,
    contact_email: str,
    contact_telephone: str,
    langue_forcee: str | None = None,
    titre_key_value_custom: str | None = None,
    instructions_supplementaires: str = "",
) -> tuple[str, str, str]:
    """Génère un PDF draft et le stocke dans cvs_generes_drafts/.

    Retourne (draft_id, langue_effective, titre_key_value_effectif).
    """
    pdf_bytes, langue_eff, titre_eff = _generer_pdf_interne(
        cv_id, offre_id, contact_email, contact_telephone,
        langue_forcee=langue_forcee,
        titre_key_value_custom=titre_key_value_custom,
        instructions_supplementaires=instructions_supplementaires,
    )

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft_id = str(uuid.uuid4())
    chemin = DRAFTS_DIR / f"{cv_id}_{offre_id}_{draft_id}.pdf"
    chemin.write_bytes(pdf_bytes)
    logger.info("Draft généré : %s", chemin)
    return draft_id, langue_eff, titre_eff


def confirmer_draft(
    cv_id: int,
    offre_id: int,
    draft_id: str,
    contact_email: str,
    contact_telephone: str,
) -> tuple[str, int]:
    """Déplace le draft vers cvs_generes/ et l'insère en BDD.

    Retourne (chemin_final, version).
    """
    chemin_draft = DRAFTS_DIR / f"{cv_id}_{offre_id}_{draft_id}.pdf"
    if not chemin_draft.exists():
        # Fallback : chercher par uuid seul (nommage partiel)
        matches = list(DRAFTS_DIR.glob(f"*_{draft_id}.pdf"))
        if not matches:
            raise RuntimeError(f"Draft {draft_id} introuvable.")
        chemin_draft = matches[0]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    version = _get_version_suivante(cv_id, offre_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_fichier = f"{cv_id}_{offre_id}_v{version}_{ts}.pdf"
    chemin_final = OUTPUT_DIR / nom_fichier
    shutil.move(str(chemin_draft), str(chemin_final))
    logger.info("Draft confirmé : %s → %s", chemin_draft, chemin_final)
    _enregistrer_en_bdd(cv_id, offre_id, version, str(chemin_final), contact_email, contact_telephone)
    return str(chemin_final), version


def supprimer_draft(draft_id: str) -> None:
    """Supprime le fichier draft (best-effort, pas d'erreur si absent)."""
    for f in DRAFTS_DIR.glob(f"*_{draft_id}.pdf"):
        f.unlink(missing_ok=True)
        return
