"""Initialise la table cvs en BDD (CV.1).

Idempotent : ne touche pas la table si elle existe déjà
avec les bonnes colonnes.
"""
import sys
sys.path.insert(0, '.')
from src.storage.database import _connexion

SCHEMA = """
CREATE TABLE IF NOT EXISTS cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_fichier TEXT NOT NULL UNIQUE,
    chemin_relatif TEXT NOT NULL,
    texte_brut TEXT,
    date_modification_fichier TIMESTAMP,
    date_ajout TIMESTAMP DEFAULT (datetime('now')),
    date_dernier_scan TIMESTAMP
);
"""


def main():
    with _connexion() as conn:
        conn.executescript(SCHEMA)
    print("[OK] Table cvs créée (ou déjà existante)")


if __name__ == "__main__":
    main()
