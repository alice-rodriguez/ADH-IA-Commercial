"""Ajout d'un CV depuis un PDF (CV.4).

Fonctions utilisées par le endpoint POST /api/cvs/upload.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ajouter_cv_depuis_pdf(chemin_pdf: Path) -> int:
    """Extrait le texte du PDF et insère le CV en BDD.

    Args:
        chemin_pdf: Chemin vers le fichier PDF (déjà sauvegardé sur disque).

    Returns:
        cv_id du CV créé.

    Raises:
        ValueError: si le PDF est illisible ou le texte extrait trop court.
    """
    from src.cvs.extraction import extraire_texte_pdf
    from src.storage.database import _connexion

    texte = extraire_texte_pdf(str(chemin_pdf))
    if len(texte) < 100:
        raise ValueError(
            f"Texte extrait trop court ({len(texte)} car.) — PDF illisible ou vide"
        )

    nom_fichier = chemin_pdf.name
    chemin_relatif = str(chemin_pdf).replace("\\", "/")
    mtime = chemin_pdf.stat().st_mtime

    with _connexion() as conn:
        cur = conn.execute(
            """
            INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut,
                             date_modification_fichier, date_dernier_scan)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (nom_fichier, chemin_relatif, texte, mtime),
        )
        cv_id = cur.lastrowid

    logger.info("CV ajouté : %s (id=%d, %d car.)", nom_fichier, cv_id, len(texte))
    return cv_id


def profiler_un_cv(cv_id: int) -> dict:
    """Profile un CV existant en BDD via Haiku et met à jour ses colonnes.

    Args:
        cv_id: ID du CV à profiler.

    Returns:
        Dict de profilage avec listes Python pour competences_techniques et domaines.

    Raises:
        ValueError: si le CV est introuvable ou si Haiku échoue.
    """
    from src.cvs.profilage import profiler_cv
    from src.storage.database import _connexion

    with _connexion() as conn:
        row = conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()

    if row is None:
        raise ValueError(f"CV id={cv_id} introuvable en BDD")

    texte_brut = row["texte_brut"] or ""
    profil = profiler_cv(texte_brut)
    if profil is None:
        raise ValueError("Profilage Haiku échoué (clé API manquante ou erreur réseau)")

    with _connexion() as conn:
        conn.execute(
            """
            UPDATE cvs SET
                nom_candidat             = ?,
                titre_courant            = ?,
                competences_techniques   = ?,
                domaines                 = ?,
                annees_experience        = ?,
                types_contrat_souhaites  = ?,
                localisation_preferee    = ?,
                tjm_moyen                = ?,
                salaire_souhaite         = ?,
                date_dernier_profilage   = datetime('now')
            WHERE id = ?
            """,
            (
                profil.get("nom_candidat"),
                profil.get("titre_courant"),
                json.dumps(profil.get("competences_techniques") or [], ensure_ascii=False),
                json.dumps(profil.get("domaines") or [], ensure_ascii=False),
                profil.get("annees_experience"),
                json.dumps(profil.get("types_contrat_souhaites") or [], ensure_ascii=False),
                profil.get("localisation_preferee"),
                profil.get("tjm_moyen"),
                profil.get("salaire_souhaite"),
                cv_id,
            ),
        )

    logger.info("CV profilé : id=%d → %s", cv_id, profil.get("nom_candidat"))
    return profil
