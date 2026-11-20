"""
FANTÔMES-01 (ménage) — Lister les offres dont l'URL n'appartient à aucune source connue.

LECTURE SEULE : rien n'est modifié ni supprimé. La liste sert à décider, avec Alice,
ce qu'il faut faire des offres suspectes (ex. l'offre de test « Business Analyst Finance »,
https://example.com/2).

Domaines connus : ceux des collecteurs (config/sources.yaml) et de leurs annonces.
Les offres « Manuelle » sont listées à part : leur lien pointe légitimement vers
n'importe quel site (annonce collée par Alice).

Usage (depuis la racine du dépôt) :
  py scripts\\offres_url_inconnues.py --db data\\offers.db
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent

# Domaine (et sous-domaines) des annonces de chaque source collectée
DOMAINES_CONNUS = (
    "free-work.com", "hellowork.com", "boamp.fr", "opendatasoft.com", "apec.fr",
    "indeed.com", "indeed.fr", "welcometothejungle.com", "freelance.com",
)


def domaine_connu(url: str | None) -> bool:
    hote = urlparse(url or "").netloc.lower().split(":")[0]
    return any(hote == d or hote.endswith("." + d) for d in DOMAINES_CONNUS)


def lister(db: Path) -> tuple[list[dict], list[dict]]:
    """(suspectes, manuelles_hors_sources) — base ouverte en lecture seule."""
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT id, source, titre, entreprise, url, date_collecte FROM offres ORDER BY date_collecte")]
    conn.close()
    inconnues = [r for r in rows if not domaine_connu(r["url"])]
    return ([r for r in inconnues if r["source"] != "Manuelle"],
            [r for r in inconnues if r["source"] == "Manuelle"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offres dont l'URL n'appartient à aucune source connue (lecture seule).")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", str(ROOT / "data" / "offers.db")))
    args = ap.parse_args(argv)
    db = Path(args.db)
    if not db.exists():
        print(f"Base introuvable : {db}")
        return 1
    suspectes, manuelles = lister(db)
    print(f"Base : {db.resolve()} (lecture seule)\n")
    print(f"OFFRES SUSPECTES (source collectée, URL hors des domaines connus) : {len(suspectes)}")
    for r in suspectes:
        print(f"  id={r['id']:<6} {r['source'] or '?':<12} {(r['date_collecte'] or '')[:10]}  "
              f"{(r['titre'] or '')[:50]:<50} {r['url'] or '(pas d URL)'}")
    print(f"\nOffres « Manuelle » pointant hors des sources collectées (normal, pour information) : {len(manuelles)}")
    for r in manuelles:
        print(f"  id={r['id']:<6} {(r['date_collecte'] or '')[:10]}  {(r['titre'] or '')[:50]:<50} {r['url'] or '(texte collé, pas d URL)'}")
    print("\nAucune modification n'a été faite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
