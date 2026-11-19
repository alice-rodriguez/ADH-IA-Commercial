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
    from src.storage.database import _connexion, migrer_cvs

    migrer_cvs()
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
                -- Nom corrigé à la main (drapeau à 1) : jamais écrasé
                nom_candidat             = CASE WHEN COALESCE(nom_modifie_manuellement, 0) = 1
                                                THEN nom_candidat ELSE ? END,
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


DOSSIER_CVS = Path("cvs")                       # même dossier que l'upload et le scan
DOSSIER_ANCIENS = DOSSIER_CVS / "_remplaces"    # hors du glob cvs/*.pdf du scan


def remplacer_cv(cv_id: int, contenu_pdf: bytes) -> dict:
    """Remplace le PDF d'un candidat existant, puis ré-extrait, re-profile et re-matche CE candidat.

    - Le fichier garde le nom existant du candidat (cvs/<nom_fichier>) : pas de second candidat.
    - Le nouveau PDF est d'abord lu à part : s'il est illisible, rien n'est modifié.
    - L'ancien PDF est conservé dans cvs/_remplaces/ (horodaté).
    - Seules les colonnes extraites du CV changent (texte, puis profil). Les saisies ADH
      (commentaires, postes ciblés, profil personnalisé, notes d'expériences, statut…)
      ne sont jamais écrites ici ; le nom n'est pas écrasé si nom_modifie_manuellement = 1.
    - Échec du profilage : signalé dans le résultat, le nouveau fichier et son texte restent.

    Raises:
        LookupError: candidat introuvable.
        ValueError: PDF illisible ou texte trop court (aucune modification faite).
    """
    import shutil
    import tempfile
    from datetime import datetime

    from src.cvs.extraction import extraire_texte_pdf
    from src.matching.calculer import recalculer_pour_cv
    from src.storage.database import _connexion, migrer_cvs

    migrer_cvs()
    with _connexion() as conn:
        row = conn.execute("SELECT nom_fichier FROM cvs WHERE id = ?", (cv_id,)).fetchone()
    if row is None:
        raise LookupError(f"CV id={cv_id} introuvable en BDD")
    nom_fichier = row["nom_fichier"]

    # 1. Lecture du nouveau PDF AVANT de toucher à l'existant
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with open(fd, "wb") as f:
            f.write(contenu_pdf)
        try:
            texte = extraire_texte_pdf(tmp)
        except Exception as e:
            raise ValueError(f"PDF illisible : {e}") from e
    finally:
        Path(tmp).unlink(missing_ok=True)
    if len(texte) < 100:
        raise ValueError(f"Texte extrait trop court ({len(texte)} car.) — PDF illisible ou vide")

    # 2. Remplacement du fichier sous le MÊME nom (ancien PDF archivé)
    DOSSIER_CVS.mkdir(exist_ok=True)
    destination = DOSSIER_CVS / nom_fichier
    ancien = None
    if destination.exists():
        DOSSIER_ANCIENS.mkdir(exist_ok=True)
        ancien = DOSSIER_ANCIENS / f"{destination.stem}_{datetime.now():%Y%m%d-%H%M%S}{destination.suffix}"
        shutil.copy2(destination, ancien)
    destination.write_bytes(contenu_pdf)

    # 3. Texte et date du fichier (le scan ne re-profilera pas une seconde fois)
    with _connexion() as conn:
        conn.execute(
            """
            UPDATE cvs SET texte_brut = ?, chemin_relatif = ?,
                           date_modification_fichier = ?, date_dernier_scan = datetime('now')
            WHERE id = ?
            """,
            (texte, str(destination).replace("\\", "/"), destination.stat().st_mtime, cv_id),
        )
    logger.info("CV remplacé : %s (id=%d, %d car.)", nom_fichier, cv_id, len(texte))

    resultat = {"cv_id": cv_id, "nom_fichier": nom_fichier, "nb_caracteres": len(texte),
                "ancien_fichier": str(ancien).replace("\\", "/") if ancien else None,
                "profilage_reussi": False, "erreur_profilage": None,
                "matching_reussi": False, "nb_matchings": 0}

    # 4. Profilage de CE candidat (fonction existante)
    try:
        profiler_un_cv(cv_id)
        resultat["profilage_reussi"] = True
    except Exception as e:
        logger.warning("Profilage échoué après remplacement du CV id=%d : %s", cv_id, e)
        resultat["erreur_profilage"] = str(e)

    # 5. Matching de CE candidat
    try:
        resultat["nb_matchings"] = recalculer_pour_cv(cv_id)
        resultat["matching_reussi"] = True
    except Exception as e:
        logger.warning("Matching échoué après remplacement du CV id=%d : %s", cv_id, e)
    return resultat
