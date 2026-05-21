"""Initialise la table analyses_ia en BDD (CV.2.bis.3.ter).

Idempotent : CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
"""
import sys
sys.path.insert(0, '.')
from src.storage.database import _connexion

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses_ia (
    cv_id                INTEGER NOT NULL,
    offre_id             INTEGER NOT NULL,
    score_ia             INTEGER,
    verdict              TEXT,
    explication          TEXT,
    points_forts         TEXT,
    points_faibles       TEXT,
    questions_a_poser    TEXT,
    date_analyse         TIMESTAMP DEFAULT (datetime('now')),
    PRIMARY KEY (cv_id, offre_id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_ia_cv
    ON analyses_ia(cv_id);

CREATE INDEX IF NOT EXISTS idx_analyses_ia_offre
    ON analyses_ia(offre_id);

CREATE INDEX IF NOT EXISTS idx_analyses_ia_date
    ON analyses_ia(date_analyse DESC);
"""


def main():
    with _connexion() as conn:
        conn.executescript(SCHEMA)
    print("[OK] Table analyses_ia créée (ou déjà existante)")


if __name__ == "__main__":
    main()
