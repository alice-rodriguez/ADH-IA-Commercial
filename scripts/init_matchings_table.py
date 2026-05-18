"""Initialise la table matchings en BDD (CV.3.A).

Idempotent : CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
"""
import sys
sys.path.insert(0, '.')
from src.storage.database import _connexion

SCHEMA = """
CREATE TABLE IF NOT EXISTS matchings (
    cv_id              INTEGER NOT NULL,
    offre_id           INTEGER NOT NULL,
    score_global       INTEGER NOT NULL,
    score_competences  INTEGER NOT NULL,
    score_domaine      INTEGER NOT NULL,
    score_experience   INTEGER NOT NULL,
    score_contrat      INTEGER NOT NULL,
    score_lieu         INTEGER NOT NULL,
    details_json       TEXT,
    date_calcul        TIMESTAMP DEFAULT (datetime('now')),
    PRIMARY KEY (cv_id, offre_id)
);

CREATE INDEX IF NOT EXISTS idx_matchings_offre_score
    ON matchings(offre_id, score_global DESC);

CREATE INDEX IF NOT EXISTS idx_matchings_cv_score
    ON matchings(cv_id, score_global DESC);
"""


def main():
    with _connexion() as conn:
        conn.executescript(SCHEMA)
    print("[OK] Table matchings créée (ou déjà existante)")


if __name__ == "__main__":
    main()
