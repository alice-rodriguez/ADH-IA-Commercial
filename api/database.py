"""
Accès à la BDD SQLite pour l'API web.

Réutilise DB_PATH et _connexion() depuis src/storage/database.py
pour ne pas dupliquer la configuration.
"""

import json
import sys
from pathlib import Path
from typing import Optional

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


_SELECT_OFFRE = """
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
"""


def get_offre_par_id(offre_id: int) -> dict | None:
    """
    Retourne UNE offre par son id, avec actions_utilisateur jointes.
    Retourne None si l'offre n'existe pas.
    Pas de filtre temporel — accessible même si > 30 jours.
    """
    with _connexion() as conn:
        row = conn.execute(
            _SELECT_OFFRE + "WHERE o.id = ?",
            (offre_id,),
        ).fetchone()

    if row is None:
        return None
    return {
        **dict(row),
        "vue": bool(row["vue"]),
        "favori": bool(row["favori"]),
    }


# ── Actions utilisateur (UPSERT sur actions_utilisateur) ──────────────────────


def offre_existe(offre_id: int) -> bool:
    """Vérifie qu'une offre existe avant tout UPDATE/INSERT."""
    with _connexion() as conn:
        row = conn.execute(
            "SELECT 1 FROM offres WHERE id = ?",
            (offre_id,),
        ).fetchone()
    return row is not None


def marquer_vue(offre_id: int) -> None:
    """UPSERT : vue=1, date_modification=now. Idempotent."""
    with _connexion() as conn:
        conn.execute(
            """
            INSERT INTO actions_utilisateur (offre_id, vue, date_modification)
            VALUES (?, 1, datetime('now'))
            ON CONFLICT(offre_id) DO UPDATE SET
                vue = 1,
                date_modification = datetime('now')
            """,
            (offre_id,),
        )


def maj_favori(offre_id: int, favori: bool) -> None:
    """UPSERT favori. Préserve les autres champs si l'entrée existe déjà."""
    with _connexion() as conn:
        conn.execute(
            """
            INSERT INTO actions_utilisateur (offre_id, favori, date_modification)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(offre_id) DO UPDATE SET
                favori = excluded.favori,
                date_modification = datetime('now')
            """,
            (offre_id, 1 if favori else 0),
        )


def maj_statut(offre_id: int, statut: str) -> None:
    """UPSERT statut. Préserve les autres champs."""
    with _connexion() as conn:
        conn.execute(
            """
            INSERT INTO actions_utilisateur (offre_id, statut, date_modification)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(offre_id) DO UPDATE SET
                statut = excluded.statut,
                date_modification = datetime('now')
            """,
            (offre_id, statut),
        )


def maj_notes(offre_id: int, notes: Optional[str]) -> None:
    """UPSERT notes. None = effacer les notes."""
    with _connexion() as conn:
        conn.execute(
            """
            INSERT INTO actions_utilisateur (offre_id, notes, date_modification)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(offre_id) DO UPDATE SET
                notes = excluded.notes,
                date_modification = datetime('now')
            """,
            (offre_id, notes),
        )


# ── Matching CVs ↔ Offres ────────────────────────────────────────────────────


def get_candidats_par_offre(offre_id: int, limit: int = 20) -> list[dict]:
    """Retourne les CVs matchés pour une offre, triés par score_global DESC."""
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id            AS cv_id,
                c.nom_fichier,
                c.nom_candidat,
                c.titre_courant,
                c.annees_experience,
                c.localisation_preferee,
                m.score_global,
                m.score_competences,
                m.score_domaine,
                m.score_experience,
                m.score_contrat,
                m.score_lieu,
                m.details_json,
                m.date_calcul
            FROM matchings m
            JOIN cvs c ON c.id = m.cv_id
            WHERE m.offre_id = ?
            ORDER BY m.score_global DESC
            LIMIT ?
            """,
            (offre_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_cvs() -> list[dict]:
    """Retourne tous les CVs triés par nom_candidat puis nom_fichier."""
    with _connexion() as conn:
        rows = conn.execute(
            "SELECT * FROM cvs ORDER BY nom_candidat ASC, nom_fichier ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_cv_par_id(cv_id: int) -> Optional[dict]:
    """Retourne un CV par son id ou None."""
    with _connexion() as conn:
        row = conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()
    return dict(row) if row else None


def cv_existe(cv_id: int) -> bool:
    """Vérifie qu'un CV existe avant tout UPDATE."""
    with _connexion() as conn:
        row = conn.execute("SELECT 1 FROM cvs WHERE id = ?", (cv_id,)).fetchone()
    return row is not None


def maj_notes_adh(cv_id: int, notes: dict) -> None:
    """UPDATE partiel des Notes ADH. Seuls les champs fournis sont mis à jour."""
    champs_autorises = {
        'tjm_negocie', 'salaire_negocie', 'postes_cibles', 'mobilite',
        'disponibilite', 'commentaires_adh', 'statut_relation',
        'date_dernier_contact',
    }
    updates = {k: v for k, v in notes.items() if k in champs_autorises}
    if not updates:
        raise ValueError("Aucun champ Notes ADH à mettre à jour.")

    cols = ", ".join(f"{k} = ?" for k in updates) + \
           ", date_modif_notes_adh = datetime('now')"
    values = list(updates.values()) + [cv_id]

    with _connexion() as conn:
        conn.execute(f"UPDATE cvs SET {cols} WHERE id = ?", values)


def compter_candidats_par_offre(score_min: int = 40) -> dict[int, int]:
    """Retourne {offre_id: nb_candidats} pour les candidats avec score_global >= score_min."""
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT offre_id, COUNT(*) as n
            FROM matchings
            WHERE score_global >= ?
            GROUP BY offre_id
            """,
            (score_min,),
        ).fetchall()
    return {r["offre_id"]: r["n"] for r in rows}


def get_top_score_par_offre(score_min: int = 40) -> dict[int, int]:
    """Retourne {offre_id: meilleur_score} parmi les candidats >= score_min."""
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT offre_id, MAX(score_global) as top
            FROM matchings
            WHERE score_global >= ?
            GROUP BY offre_id
            """,
            (score_min,),
        ).fetchall()
    return {r["offre_id"]: r["top"] for r in rows}


# ── Analyses IA ─────────────────────────────────────────────────────────────


def get_analyse_ia(cv_id: int, offre_id: int) -> dict | None:
    """Retourne l'analyse IA stockée ou None si absente."""
    with _connexion() as conn:
        row = conn.execute(
            "SELECT * FROM analyses_ia WHERE cv_id = ? AND offre_id = ?",
            (cv_id, offre_id),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    for key in ("points_forts", "points_faibles", "questions_a_poser"):
        raw = d.get(key)
        try:
            d[key] = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            d[key] = []
    return d


def upsert_analyse_ia(cv_id: int, offre_id: int, analyse: dict) -> None:
    """UPSERT de l'analyse IA (INSERT OR REPLACE)."""
    with _connexion() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses_ia
                (cv_id, offre_id, score_ia, verdict, explication,
                 points_forts, points_faibles, questions_a_poser, date_analyse)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                cv_id,
                offre_id,
                analyse.get("score_ia"),
                analyse.get("verdict"),
                analyse.get("explication"),
                json.dumps(analyse.get("points_forts", []), ensure_ascii=False),
                json.dumps(analyse.get("points_faibles", []), ensure_ascii=False),
                json.dumps(analyse.get("questions_a_poser", []), ensure_ascii=False),
            ),
        )


def get_offres_par_cv(cv_id: int, limit: int = 20) -> list[dict]:
    """Retourne les offres matchées pour un CV, triées par score_global DESC."""
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT
                o.id            AS offre_id,
                o.titre,
                o.entreprise,
                o.lieu,
                o.type_contrat_clarifie,
                o.source,
                o.url,
                o.date_collecte,
                m.score_global,
                m.score_competences,
                m.score_domaine,
                m.score_experience,
                m.score_contrat,
                m.score_lieu,
                m.date_calcul
            FROM matchings m
            JOIN offres o ON o.id = m.offre_id
            WHERE m.cv_id = ?
            ORDER BY m.score_global DESC
            LIMIT ?
            """,
            (cv_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
