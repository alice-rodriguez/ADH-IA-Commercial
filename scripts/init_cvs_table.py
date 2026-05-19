"""Initialise la table cvs en BDD (CV.1 + CV.2).

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

COLONNES_AJOUTEES = [
    ('nom_candidat',             'TEXT'),
    ('titre_courant',            'TEXT'),
    ('competences_techniques',   'TEXT'),
    ('domaines',                 'TEXT'),
    ('annees_experience',        'INTEGER'),
    ('types_contrat_souhaites',  'TEXT'),
    ('localisation_preferee',    'TEXT'),
    ('tjm_moyen',                'INTEGER'),
    ('salaire_souhaite',         'INTEGER'),
    ('date_dernier_profilage',   'TIMESTAMP'),
    # Notes ADH (CV.2.bis.1)
    ('tjm_negocie',              'INTEGER'),
    ('salaire_negocie',          'INTEGER'),
    ('postes_cibles',            'TEXT'),
    ('mobilite',                 'TEXT'),
    ('disponibilite',            'TEXT'),
    ('commentaires_adh',         'TEXT'),
    ('statut_relation',          "TEXT DEFAULT 'actif'"),
    ('date_dernier_contact',     'DATE'),
    ('date_modif_notes_adh',     'TIMESTAMP'),
]


def _colonne_existe(conn, table: str, colonne: str) -> bool:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row['name'] == colonne for row in cursor)


def main():
    with _connexion() as conn:
        conn.executescript(SCHEMA)
        for col, type_ in COLONNES_AJOUTEES:
            if not _colonne_existe(conn, 'cvs', col):
                conn.execute(f"ALTER TABLE cvs ADD COLUMN {col} {type_}")
                print(f"[+] Colonne {col} ajoutée")
    print("[OK] Table cvs à jour")


if __name__ == "__main__":
    main()
