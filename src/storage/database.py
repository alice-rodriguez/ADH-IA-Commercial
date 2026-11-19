"""
Base de données SQLite — stockage des offres et déduplication.

Rôle : mémoriser toutes les offres collectées, gérer la déduplication,
et exposer les données à l'interface web (favoris, notes, statuts).
"""

import sqlite3
import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "data/offers.db"))


# ── Fraîcheur des offres ─────────────────────────────────────────────────────
# Une offre n'est pas jugée sur son âge mais sur sa fraîcheur CONSTATÉE :
# date_derniere_vue est mise à jour chaque fois qu'un collecteur la retrouve sur
# son site. Une offre qui cesse d'être revue a disparu de sa source.
#
# Elle est PÉRIMÉE (masquée partout, jamais supprimée) si :
#   - elle n'a pas été revue depuis plus de JOURS_SANS_REVUE_MAX jours : 21 jours
#     et non quelques-uns, car une offre peut sortir de la profondeur de
#     pagination d'un collecteur sans être retirée du site ;
#   - OU elle a été collectée il y a plus de AGE_MAX_JOURS jours : au-delà, même
#     revue, une mission est en pratique pourvue ou republiée sous une autre forme.
# Exemption : les sources que AUCUN collecteur ne revisite (offres saisies à la
# main) — leur date_derniere_vue ne bouge jamais, elles ne sont jamais périmées.
JOURS_SANS_REVUE_MAX = 21
AGE_MAX_JOURS = 60
SOURCES_SANS_REVISITE = ("Manuelle",)


def bornes_fraicheur(maintenant: datetime | None = None) -> tuple[str, str]:
    """(revue_min, collecte_min) au format des dates stockées (isoformat local)."""
    m = maintenant or datetime.now()
    return ((m - timedelta(days=JOURS_SANS_REVUE_MAX)).isoformat(),
            (m - timedelta(days=AGE_MAX_JOURS)).isoformat())


def sql_offre_active(alias: str = "o") -> tuple[str, list]:
    """Clause SQL « offre non périmée » pour la table offres aliasée `alias`, et ses paramètres."""
    revue_min, collecte_min = bornes_fraicheur()
    marques = ", ".join("?" for _ in SOURCES_SANS_REVISITE)
    clause = (
        f"({alias}.source IN ({marques}) OR ("
        f"COALESCE({alias}.date_derniere_vue, {alias}.date_collecte) >= ? "
        f"AND {alias}.date_collecte >= ?))"
    )
    return clause, [*SOURCES_SANS_REVISITE, revue_min, collecte_min]


def est_perimee(offre: dict, maintenant: datetime | None = None) -> bool:
    """Même règle que sql_offre_active, pour une offre déjà chargée (dict avec ses dates)."""
    if offre.get("source") in SOURCES_SANS_REVISITE:
        return False
    revue_min, collecte_min = bornes_fraicheur(maintenant)
    collecte = offre.get("date_collecte") or ""
    revue = offre.get("date_derniere_vue") or collecte
    return revue < revue_min or collecte < collecte_min


def hashes_actifs(hashes: list[str]) -> set[str]:
    """Parmi ces hash d'offres, ceux qui ne sont PAS périmés selon la base."""
    if not hashes:
        return set()
    clause, params = sql_offre_active("o")
    marques = ", ".join("?" for _ in hashes)
    with _connexion() as conn:
        rows = conn.execute(
            f"SELECT o.hash FROM offres o WHERE o.hash IN ({marques}) AND {clause}",
            [*hashes, *params],
        ).fetchall()
    return {r["hash"] for r in rows}


def _connexion() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialiser():
    """Crée les tables si elles n'existent pas encore. À appeler au démarrage."""
    with _connexion() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS offres (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                hash                  TEXT    UNIQUE NOT NULL,
                titre                 TEXT,
                entreprise            TEXT,
                lieu                  TEXT,
                type_contrat          TEXT,
                type_contrat_clarifie TEXT,
                source                TEXT,
                url                   TEXT,
                description           TEXT,
                resume_ia             TEXT,
                score_ia              INTEGER,
                tjm_min               INTEGER,
                tjm_max               INTEGER,
                salaire_min           INTEGER,
                salaire_max           INTEGER,
                date_collecte         TEXT    NOT NULL,
                date_derniere_vue     TEXT,
                date_envoi            TEXT,
                envoyee               INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS actions_utilisateur (
                offre_id          INTEGER PRIMARY KEY,
                vue               INTEGER DEFAULT 0,
                favori            INTEGER DEFAULT 0,
                statut            TEXT    DEFAULT 'nouveau',
                notes             TEXT,
                date_modification TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (offre_id) REFERENCES offres(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS competences_offre (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                offre_id    INTEGER NOT NULL,
                competence  TEXT    NOT NULL,
                UNIQUE(offre_id, competence),
                FOREIGN KEY (offre_id) REFERENCES offres(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_hash          ON offres(hash);
            CREATE INDEX IF NOT EXISTS idx_date_collecte ON offres(date_collecte);
            CREATE INDEX IF NOT EXISTS idx_envoyee       ON offres(envoyee);
            CREATE INDEX IF NOT EXISTS idx_score_ia      ON offres(score_ia);
            CREATE INDEX IF NOT EXISTS idx_statut        ON actions_utilisateur(statut);
            CREATE INDEX IF NOT EXISTS idx_competence    ON competences_offre(competence);
        """)

        # Migration idempotente : une base créée avant l'ajout de tjm_min/tjm_max
        # au schéma n'a pas ces colonnes (CREATE TABLE IF NOT EXISTS ne modifie
        # jamais une table existante), et sauvegarder() les écrit.
        colonnes = {row[1] for row in conn.execute("PRAGMA table_info(offres)")}
        for colonne in ("tjm_min", "tjm_max"):
            if colonne not in colonnes:
                conn.execute(f"ALTER TABLE offres ADD COLUMN {colonne} INTEGER")
                logger.info("Migration : colonne offres.%s ajoutée", colonne)

        # date_derniere_vue : dernière fois que l'offre a été vue en ligne.
        # Initialisée à date_collecte pour les offres existantes, sinon le
        # signal serait vide jusqu'au prochain passage de chaque offre.
        if "date_derniere_vue" not in colonnes:
            conn.execute("ALTER TABLE offres ADD COLUMN date_derniere_vue TEXT")
            conn.execute("UPDATE offres SET date_derniere_vue = date_collecte")
            logger.info("Migration : colonne offres.date_derniere_vue ajoutée "
                        "(initialisée à date_collecte)")
    migrer_cvs()
    migrer_matchings()
    migrer_parametres()
    logger.info("Base de données prête : %s", DB_PATH)


def migrer_parametres():
    """Migration idempotente : crée la table parametres (clé → valeur) si absente.

    Paramètres applicatifs modifiables depuis l'interface (ex. cv_instructions_defaut).
    Stockés en base, et non dans un fichier de config, pour survivre à un git pull.
    """
    with _connexion() as conn:
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'parametres'"
        ).fetchone()
        if not existe:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parametres (
                    cle    TEXT PRIMARY KEY,
                    valeur TEXT
                )
            """)
            logger.info("Migration : table parametres créée")


def get_parametre(cle: str, defaut: str = "") -> str:
    """Valeur d'un paramètre applicatif ; `defaut` s'il n'a jamais été enregistré."""
    migrer_parametres()   # l'API ne passe pas par initialiser() : table garantie ici
    with _connexion() as conn:
        row = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    if row is None or row["valeur"] is None:
        return defaut
    return row["valeur"]


def set_parametre(cle: str, valeur: str) -> None:
    """Enregistre (crée ou remplace) la valeur d'un paramètre applicatif."""
    migrer_parametres()
    with _connexion() as conn:
        conn.execute(
            "INSERT INTO parametres (cle, valeur) VALUES (?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            (cle, valeur),
        )


def migrer_cvs():
    """Migration idempotente de la table cvs (créée par scripts/init_cvs_table.py).

    Ajoute nom_modifie_manuellement si absente : drapeau mis à 1 quand le nom
    est corrigé à la main, pour que le re-profilage ne l'écrase pas.
    Sans effet si la table cvs n'existe pas encore.
    """
    with _connexion() as conn:
        colonnes = {row[1] for row in conn.execute("PRAGMA table_info(cvs)")}
        if colonnes and "nom_modifie_manuellement" not in colonnes:
            conn.execute("ALTER TABLE cvs ADD COLUMN nom_modifie_manuellement INTEGER DEFAULT 0")
            logger.info("Migration : colonne cvs.nom_modifie_manuellement ajoutée")


def migrer_matchings():
    """Migration idempotente de la table matchings (créée par scripts/init_matchings_table.py).

    Ajoute ajout_manuel si absente : 1 = candidat positionné à la main par Alice
    sur l'offre (toujours affiché, préservé par les recalculs).
    Sans effet si la table matchings n'existe pas encore.
    """
    with _connexion() as conn:
        colonnes = {row[1] for row in conn.execute("PRAGMA table_info(matchings)")}
        if colonnes and "ajout_manuel" not in colonnes:
            conn.execute("ALTER TABLE matchings ADD COLUMN ajout_manuel INTEGER DEFAULT 0")
            logger.info("Migration : colonne matchings.ajout_manuel ajoutée")


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

    Offre déjà connue (même hash) : seule date_derniere_vue est mise à jour ;
    date_collecte (première fois vue) et les autres champs ne bougent pas.
    """
    hash_offre = _calculer_hash(
        offre.get("titre", ""),
        offre.get("entreprise", ""),
        offre.get("source", ""),
    )

    fenetre = offre.get("fenetre_deduplication_jours", 7)
    date_limite = (datetime.now() - timedelta(days=fenetre)).isoformat()
    maintenant = datetime.now().isoformat()

    with _connexion() as conn:
        # Offre revue : on trace son passage (aucun effet si le hash est nouveau)
        try:
            conn.execute(
                "UPDATE offres SET date_derniere_vue = ? WHERE hash = ?",
                (maintenant, hash_offre),
            )
        except sqlite3.Error as e:
            logger.error("Erreur MAJ date_derniere_vue '%s': %s", offre.get("titre"), e)

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
                  (hash, titre, entreprise, lieu, type_contrat, source, url, description,
                   tjm_min, tjm_max, date_collecte, date_derniere_vue)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    offre.get("tjm_min"),
                    offre.get("tjm_max"),
                    maintenant,
                    maintenant,
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
