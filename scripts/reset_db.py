"""
Reset complet de la base de données SQLite.

ATTENTION : supprime définitivement data/offers.db.
Les offres seront re-collectées au prochain run GitHub Actions.

Usage : python scripts/reset_db.py
"""

import sys
import sqlite3
from pathlib import Path

# Accès au module src/ depuis la racine du projet
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.database import DB_PATH, initialiser


def compter_colonnes(db_path: Path, table: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def main():
    print("=" * 55)
    print("  RESET BASE DE DONNÉES — ADH-IA-Commercial")
    print("=" * 55)

    if DB_PATH.exists():
        print(f"\n  Base actuelle : {DB_PATH} ({DB_PATH.stat().st_size // 1024} Ko)")
    else:
        print(f"\n  Aucune base existante à {DB_PATH}")

    print()
    reponse = input("  Supprimer offers.db et recréer le schéma ? [y/N] : ").strip().lower()
    if reponse != "y":
        print("\n  Annulé. Aucune modification.")
        sys.exit(0)

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"\n  ✓ {DB_PATH} supprimée.")

    initialiser()
    print(f"  ✓ Nouveau schéma créé.")

    TABLES = ["offres", "actions_utilisateur", "competences_offre"]
    print(f"\n  Tables créées : {len(TABLES)}")
    for table in TABLES:
        colonnes = compter_colonnes(DB_PATH, table)
        print(f"    • {table:<25} {len(colonnes)} colonnes : {', '.join(colonnes)}")

    print()
    print("  Reset terminé. Le prochain run GitHub Actions re-peuplera la base.")
    print("=" * 55)


if __name__ == "__main__":
    main()
