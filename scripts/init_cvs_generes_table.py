"""Crée la table cvs_generes si elle n'existe pas (idempotent)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.database import _connexion

SCHEMA = """
CREATE TABLE IF NOT EXISTS cvs_generes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cv_id INTEGER NOT NULL,
    offre_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    chemin_fichier TEXT NOT NULL,
    date_generation TIMESTAMP DEFAULT (datetime('now')),
    contact_email TEXT,
    contact_telephone TEXT,
    instructions_modifications TEXT,
    FOREIGN KEY (cv_id) REFERENCES cvs(id) ON DELETE CASCADE,
    FOREIGN KEY (offre_id) REFERENCES offres(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cvs_generes_cv_offre
    ON cvs_generes(cv_id, offre_id);
"""

if __name__ == "__main__":
    with _connexion() as conn:
        conn.executescript(SCHEMA)
    print("[OK] Table cvs_generes créée (ou déjà existante)")
