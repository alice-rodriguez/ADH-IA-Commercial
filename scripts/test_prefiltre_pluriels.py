"""
CORRECTIF-11 — Pré-filtre : verdicts AVANT / APRÈS la tolérance pluriels / féminins.

Lecture seule : aucune écriture en base, aucun appel réseau, aucun appel IA.

  a) Titres de référence : verdict avant / après.
  b) Si une base est présente (DB_PATH ou data/*.db) : rejeu du pré-filtre sur
     toutes les offres, bascules rejet ↔ acceptation.

"AVANT" = src/filters/keyword_filter.py tel qu'au commit REF_AVANT (lu via git),
"APRÈS" = le fichier du répertoire de travail.

Usage (depuis la racine du dépôt) :
  python scripts/test_prefiltre_pluriels.py
  python scripts/test_prefiltre_pluriels.py --ref 50f4e7c --db data/offers.db
"""

import argparse
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REF_AVANT = "50f4e7c"   # dernier commit avant CORRECTIF-11

TITRES = [
    # Cas mesurés (spec)
    "Chef de Projets M365 et Telecom Senior - Freelance H/F",
    "Chef de Projet M365 banque",
    "Chef de Projets banque",
    "Business Analyst - Chef de Projet IT Trading H/F",
    # Variantes ajoutées
    "Chefs de projet banque",
    "Chargée de projet assurance",
    "Stages chef de projet banque",                    # terme exclu au pluriel
    # Cas réel perdu le 04/11 (HelloWork)
    "Chef de Projets M365 et Télécom Sénior - Freelance H/F",
    # Limites / effets de bord à connaître
    "Cheffe de projet banque",                         # féminin en "-fe"
    "Architecte cloud - banque - Pays-Bas",            # sigle BA : ne doit PAS trouver "bas"
]


def charger_avant(ref: str):
    """Charge keyword_filter.py tel qu'au commit `ref`, comme module isolé."""
    try:
        source = subprocess.run(
            ["git", "show", f"{ref}:src/filters/keyword_filter.py"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except Exception as e:
        sys.exit(f"Impossible de lire la version AVANT ({ref}) via git : {e}")
    chemin = Path(tempfile.gettempdir()) / f"keyword_filter_avant_{ref}.py"
    chemin.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("keyword_filter_avant", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict(module, offre: dict, criteres: dict) -> str:
    ok, score, raison = module.evaluer(dict(offre), criteres)
    return f"ACCEPTÉ (score={score})" if ok else f"REJET — {raison}"


def trouver_db(arg: str | None) -> Path | None:
    if arg:
        return Path(arg)
    if os.getenv("DB_PATH"):
        p = Path(os.environ["DB_PATH"])
        return p if p.is_absolute() else ROOT / p
    bases = sorted((ROOT / "data").glob("*.db")) if (ROOT / "data").is_dir() else []
    return bases[0] if bases else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=REF_AVANT, help="commit de la version AVANT")
    ap.add_argument("--db", default=None, help="chemin de la base (défaut : DB_PATH ou data/*.db)")
    args = ap.parse_args()

    from src.filters import keyword_filter as apres
    avant = charger_avant(args.ref)
    with open(ROOT / "config" / "criteria.yaml", encoding="utf-8") as f:
        criteres = yaml.safe_load(f)

    print("=" * 100)
    print(f"a) TITRES DE RÉFÉRENCE — AVANT = {args.ref}, APRÈS = répertoire de travail")
    print("=" * 100)
    for titre in TITRES:
        offre = {"titre": titre, "description": "", "entreprise": ""}
        va, vp = verdict(avant, offre, criteres), verdict(apres, offre, criteres)
        marque = "  " if va == vp else "≠ "
        print(f"{marque}{titre}")
        print(f"     AVANT : {va}")
        print(f"     APRÈS : {vp}")

    print()
    print("=" * 100)
    db = trouver_db(args.db)
    if not db or not db.exists():
        print(f"b) REJEU SUR LA BASE — base introuvable ({db or 'data/*.db'}) : partie b) non exécutée")
        return
    print(f"b) REJEU SUR LA BASE — {db.resolve()} (lecture seule)")
    print("=" * 100)
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    rows = conn.execute("SELECT titre, description, entreprise, source FROM offres").fetchall()
    conn.close()

    acc_avant = acc_apres = 0
    vers_accept, vers_rejet = [], []
    for titre, description, entreprise, source in rows:
        offre = {"titre": titre or "", "description": description or "", "entreprise": entreprise or ""}
        ok_a, _, _ = avant.evaluer(dict(offre), criteres)
        ok_p, _, raison_p = apres.evaluer(dict(offre), criteres)
        acc_avant += ok_a
        acc_apres += ok_p
        if not ok_a and ok_p:
            vers_accept.append(f"[{source}] {titre}")
        elif ok_a and not ok_p:
            vers_rejet.append(f"[{source}] {titre} — {raison_p}")

    print(f"  Offres en base                         : {len(rows)}")
    print(f"  Acceptées AVANT / APRÈS                : {acc_avant} / {acc_apres}")
    print(f"  Bascules rejet → acceptation           : {len(vers_accept)}")
    print(f"  Bascules acceptation → rejet           : {len(vers_rejet)}")
    print("\n  10 premières bascules rejet → acceptation :")
    for t in vers_accept[:10]:
        print(f"    + {t}")
    print("\n  10 premières bascules acceptation → rejet :")
    for t in vers_rejet[:10]:
        print(f"    - {t}")


if __name__ == "__main__":
    main()
