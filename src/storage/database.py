"""
Base de données SQLite — stockage des offres et déduplication.

Rôle : mémoriser toutes les offres collectées pour éviter d'envoyer
deux fois la même offre dans la fenêtre de déduplication (7 jours par défaut).
"""

import sqlite3
import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "data/offers.db"))


def _connexion() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialiser():
    """Crée les tables si elles n'existent pas encore. À appeler au démarrage."""
    with _connexion() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS offres (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                hash            TEXT    UNIQUE NOT NULL,
                titre           TEXT,
                entreprise      TEXT,
                lieu            TEXT,
                type_contrat    TEXT,
                source          TEXT,
                url             TEXT,
                description     TEXT,
                resume_ia       TEXT,
                score_ia        INTEGER,
                date_collecte   TEXT    NOT NULL,
                date_envoi      TEXT,
                envoyee         INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_hash          ON offres(hash);
            CREATE INDEX IF NOT EXISTS idx_date_collecte ON offres(date_collecte);
            CREATE INDEX IF NOT EXISTS idx_envoyee       ON offres(envoyee);
        """)
    logger.info("Base de données prête : %s", DB_PATH)


def _calculer_hash(titre: str, entreprise: str, source: str) -> str:
    """Identifiant unique d'une offre basé sur son titre + entreprise + source."""
    contenu = f"{titre.lower().strip()}|{entreprise.lower().strip()}|{source}"
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def est_doublon(titre: str, entreprise: str, source: str, fenetre_jours: int = 7) -> bool:
    """Retourne True si cette offre a déjà été vue dans les N derniers jours."""
    hash_offre = _calculer_hash(titre, entreprise, source)
    date_limite = (datetime.now() - timedelta(days=fenetre_jours)).isoformat()
    with _connexion() as conn:
        row = conn.execute(
            "SELECT id FROM offres WHERE hash = ? AND date_collecte > ?",
            (hash_offre, date_limite),
        ).fetchone()
    return row is not None


def sauvegarder(offre: dict) -> bool:
    """
    Sauvegarde une offre dans la base.
    Retourne True si sauvegardée, False si doublon (déjà vue récemment).
    """
    hash_offre = _calculer_hash(
        offre.get("titre", ""),
        offre.get("entreprise", ""),
        offre.get("source", ""),
    )

    fenetre = offre.get("fenetre_deduplication_jours", 7)
    date_limite = (datetime.now() - timedelta(days=fenetre)).isoformat()

    with _connexion() as conn:
        existing = conn.execute(
            "SELECT id FROM offres WHERE hash = ? AND date_collecte > ?",
            (hash_offre, date_limite),
        ).fetchone()
        if existing:
            return False

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO offres
                  (hash, titre, entreprise, lieu, type_contrat, source, url, description, date_collecte)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hash_offre,
                    offre.get("titre"),
                    offre.get("entreprise"),
                    offre.get("lieu"),
                    offre.get("type_contrat"),
                    offre.get("source"),
                    offre.get("url"),
                    offre.get("description"),
                    datetime.now().isoformat(),
                ),
            )
            return True
        except sqlite3.Error as e:
            logger.error("Erreur sauvegarde offre '%s': %s", offre.get("titre"), e)
            return False


def mettre_a_jour_ia(hash_offre: str, resume: str, score: int):
    """Met à jour le résumé et le score IA d'une offre après filtrage."""
    with _connexion() as conn:
        conn.execute(
            "UPDATE offres SET resume_ia = ?, score_ia = ? WHERE hash = ?",
            (resume, score, hash_offre),
        )


def get_hash(titre: str, entreprise: str, source: str) -> str:
    return _calculer_hash(titre, entreprise, source)


def get_offres_du_jour(score_minimum: int = 60) -> list[dict]:
    """Récupère les offres collectées aujourd'hui avec un score IA suffisant."""
    debut_journee = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    with _connexion() as conn:
        rows = conn.execute(
            """
            SELECT * FROM offres
            WHERE date_collecte >= ?
              AND envoyee = 0
              AND score_ia IS NOT NULL
              AND score_ia >= ?
            ORDER BY score_ia DESC
            """,
            (debut_journee, score_minimum),
        ).fetchall()
    return [dict(r) for r in rows]


def marquer_envoyees(hashes: list):
    """Marque les offres comme envoyées pour éviter de les réenvoyer demain."""
    date_envoi = datetime.now().isoformat()
    with _connexion() as conn:
        conn.executemany(
            "UPDATE offres SET envoyee = 1, date_envoi = ? WHERE hash = ?",
            [(date_envoi, h) for h in hashes],
        )
    logger.info("%d offres marquées comme envoyées", len(hashes))
