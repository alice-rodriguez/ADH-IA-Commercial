"""Calcul et persistance des scores de matching (CV.3.A).

Usage CLI :
    python -m src.matching.calculer
"""

import logging
import sys

sys.path.insert(0, ".")

from src.matching.scoring import calculer_score_global
from src.storage.database import _connexion

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def recalculer_pour_cv(cv_id: int) -> int:
    """Recalcule les scores pour un CV donné contre toutes les offres < 30 j.

    Returns:
        Nombre de scores insérés/mis à jour.
    """
    with _connexion() as conn:
        cv_row = conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()
        if cv_row is None:
            logger.warning("CV id=%d introuvable.", cv_id)
            return 0

        cv = dict(cv_row)
        if not cv.get("competences_techniques"):
            logger.info("  CV id=%d non profilé, skip.", cv_id)
            return 0

        offres = conn.execute(
            """
            SELECT * FROM offres
            WHERE date_collecte >= datetime('now', '-30 days')
            """
        ).fetchall()

        count = 0
        for offre_row in offres:
            offre = dict(offre_row)
            scores = calculer_score_global(cv, offre)
            conn.execute(
                """
                INSERT OR REPLACE INTO matchings (
                    cv_id, offre_id,
                    score_global, score_competences, score_domaine,
                    score_experience, score_contrat, score_lieu,
                    details_json, date_calcul
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    cv_id,
                    offre["id"],
                    scores["score_global"],
                    scores["score_competences"],
                    scores["score_domaine"],
                    scores["score_experience"],
                    scores["score_contrat"],
                    scores["score_lieu"],
                    scores["details_json"],
                ),
            )
            count += 1

    return count


def recalculer_tous() -> dict:
    """Recalcule les matchings pour tous les CVs profilés.

    Returns:
        Dict avec nb_cvs, nb_matchings.
    """
    with _connexion() as conn:
        cvs = conn.execute(
            "SELECT id, nom_fichier FROM cvs WHERE competences_techniques IS NOT NULL"
        ).fetchall()

    stats = {"nb_cvs": 0, "nb_matchings": 0}
    for cv_row in cvs:
        cv_id = cv_row["id"]
        nom = cv_row["nom_fichier"]
        n = recalculer_pour_cv(cv_id)
        logger.info("  CV %s (id=%d) : %d matching(s)", nom, cv_id, n)
        stats["nb_cvs"] += 1
        stats["nb_matchings"] += n

    return stats


def main():
    logger.info("=" * 60)
    logger.info("CALCUL MATCHINGS CVs ↔ OFFRES")
    logger.info("=" * 60)
    stats = recalculer_tous()
    logger.info("=" * 60)
    logger.info("Résumé :")
    logger.info("  CVs traités   : %d", stats["nb_cvs"])
    logger.info("  Matchings     : %d", stats["nb_matchings"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
