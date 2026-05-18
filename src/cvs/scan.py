"""Scan du dossier cvs/ et synchronisation avec la table cvs.

Usage : python -m src.cvs.scan
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, '.')
from src.cvs.extraction import extraire_texte_pdf
from src.storage.database import _connexion

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOSSIER_CVS = "cvs"


def scanner_dossier() -> dict:
    """Scanne cvs/ et synchronise avec la BDD.

    Returns:
        Dict avec compteurs : ajouts, mises_a_jour, inchanges, orphelins.
    """
    chemin_dossier = Path(DOSSIER_CVS)
    if not chemin_dossier.exists():
        chemin_dossier.mkdir(parents=True)
        logger.info("Dossier %s/ créé.", DOSSIER_CVS)

    pdfs = list(chemin_dossier.glob("*.pdf"))
    logger.info("Scan %s/ : %d fichier(s) PDF trouvé(s)", DOSSIER_CVS, len(pdfs))

    stats = {"ajouts": 0, "mises_a_jour": 0, "inchanges": 0, "orphelins": 0}
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
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
