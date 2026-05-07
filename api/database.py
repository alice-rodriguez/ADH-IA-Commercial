"""
Accès à la BDD SQLite pour l'API web.

Réutilise DB_PATH et _connexion() depuis src/storage/database.py
pour ne pas dupliquer la configuration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import DB_PATH, _connexion  # noqa: E402


def get_offres_recentes(jours: int = 30) -> list[dict]:
    """
    Retourne les offres collectées dans les N derniers jours.

    Inclut les données actions_utilisateur via LEFT JOIN.
    Offres sans entrée actions_utilisateur : vue=False, favori=False,
    statut='nouveau', notes=None.
    Tri : score_ia DESC NULLS LAST, puis date_collecte DESC.
    """
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT
                o.id,
                o.titre,
                o.entreprise,
                o.lieu,
                o.type_contrat,
                o.type_contrat_clarifie,
                o.source,
                o.url,
                o.description,
                o.resume_ia,
                o.score_ia,
                o.tjm_min,
                o.tjm_max,
                o.salaire_min,
                o.salaire_max,
                o.date_collecte,
                COALESCE(a.vue, 0)            AS vue,
                COALESCE(a.favori, 0)         AS favori,
                COALESCE(a.statut, 'nouveau') AS statut,
                a.notes                       AS notes
            FROM offres o
            LEFT JOIN actions_utilisateur a ON a.offre_id = o.id
            WHERE o.date_collecte >= datetime('now', '-' || ? || ' days')
            ORDER BY
                o.score_ia IS NULL,
                o.score_ia DESC,
                o.date_collecte DESC
            """,
            (jours,),
        ).fetchall()

    return [
        {
            **dict(row),
            "vue": bool(row["vue"]),
            "favori": bool(row["favori"]),
        }
        for row in rows
    ]
