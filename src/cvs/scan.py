"""Scan du dossier cvs/ et synchronisation avec la table cvs.

Usage : python -m src.cvs.scan
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, '.')
from src.cvs.extraction import extraire_texte_pdf
from src.cvs.profilage import profiler_cv
from src.matching.calculer import recalculer_tous
from src.storage.database import _connexion

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOSSIER_CVS = "cvs"


def _stocker_profil(conn, nom: str, profil: dict) -> None:
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
        WHERE nom_fichier = ?
        """,
        (
            profil.get("nom_candidat"),
            profil.get("titre_courant"),
            json.dumps(profil.get("competences_techniques") or []),
            json.dumps(profil.get("domaines") or []),
            profil.get("annees_experience"),
            json.dumps(profil.get("types_contrat_souhaites") or []),
            profil.get("localisation_preferee"),
            profil.get("tjm_moyen"),
            profil.get("salaire_souhaite"),
            nom,
        ),
    )


def scanner_dossier() -> dict:
    """Scanne cvs/ et synchronise avec la BDD.

    Returns:
        Dict avec compteurs : ajouts, mises_a_jour, inchanges, orphelins,
        profiles.
    """
    chemin_dossier = Path(DOSSIER_CVS)
    if not chemin_dossier.exists():
        chemin_dossier.mkdir(parents=True)
        logger.info("Dossier %s/ créé.", DOSSIER_CVS)

    pdfs = list(chemin_dossier.glob("*.pdf"))
    logger.info("Scan %s/ : %d fichier(s) PDF trouvé(s)", DOSSIER_CVS, len(pdfs))

    stats = {"ajouts": 0, "mises_a_jour": 0, "inchanges": 0, "orphelins": 0, "profiles": 0}
    noms_fichiers_disque = set()

    with _connexion() as conn:
        for pdf in pdfs:
            nom = pdf.name
            noms_fichiers_disque.add(nom)
            chemin_relatif = str(pdf).replace("\\", "/")
            mtime = pdf.stat().st_mtime

            row = conn.execute(
                "SELECT id, date_modification_fichier FROM cvs WHERE nom_fichier = ?",
                (nom,),
            ).fetchone()

            if row is None:
                texte = extraire_texte_pdf(str(pdf))
                conn.execute(
                    """
                    INSERT INTO cvs (
                        nom_fichier, chemin_relatif, texte_brut,
                        date_modification_fichier, date_dernier_scan
                    ) VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (nom, chemin_relatif, texte, mtime),
                )
                stats["ajouts"] += 1
                logger.info("  [+] Nouveau : %s (%d car.)", nom, len(texte))

                profil = profiler_cv(texte)
                if profil:
                    _stocker_profil(conn, nom, profil)
                    stats["profiles"] += 1
                    logger.info("  [✓] Profilé : %s (%s)", nom, profil.get("nom_candidat"))
                else:
                    logger.warning("  [?] Profilage échoué pour %s", nom)

            elif row["date_modification_fichier"] != mtime:
                texte = extraire_texte_pdf(str(pdf))
                conn.execute(
                    """
                    UPDATE cvs SET
                        texte_brut = ?,
                        date_modification_fichier = ?,
                        date_dernier_scan = datetime('now')
                    WHERE nom_fichier = ?
                    """,
                    (texte, mtime, nom),
                )
                stats["mises_a_jour"] += 1
                logger.info("  [~] Mis à jour : %s", nom)

                profil = profiler_cv(texte)
                if profil:
                    _stocker_profil(conn, nom, profil)
                    stats["profiles"] += 1
                    logger.info("  [✓] Profilé : %s (%s)", nom, profil.get("nom_candidat"))
                else:
                    logger.warning("  [?] Profilage échoué pour %s", nom)

            else:
                stats["inchanges"] += 1

        # Détection orphelins : CVs en BDD qui n'existent plus sur disque
        rows = conn.execute("SELECT nom_fichier FROM cvs").fetchall()
        for r in rows:
            if r["nom_fichier"] not in noms_fichiers_disque:
                stats["orphelins"] += 1
                logger.warning(
                    "  [!] Orphelin (en BDD mais pas sur disque) : %s",
                    r["nom_fichier"],
                )

    return stats


def main():
    logger.info("=" * 60)
    logger.info("SCAN CVs")
    logger.info("=" * 60)
    stats = scanner_dossier()
    logger.info("=" * 60)
    logger.info("Résumé :")
    logger.info("  Ajouts        : %d", stats["ajouts"])
    logger.info("  Mises à jour  : %d", stats["mises_a_jour"])
    logger.info("  Inchangés     : %d", stats["inchanges"])
    logger.info("  Orphelins     : %d", stats["orphelins"])
    logger.info("  Profilés      : %d", stats["profiles"])
    logger.info("=" * 60)

    if stats["profiles"] > 0 or stats["ajouts"] > 0 or stats["mises_a_jour"] > 0:
        logger.info("Recalcul des matchings CVs ↔ offres...")
        m = recalculer_tous()
        logger.info("  CVs matchés  : %d", m["nb_cvs"])
        logger.info("  Matchings    : %d", m["nb_matchings"])
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
