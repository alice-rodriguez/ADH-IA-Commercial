"""
FANTÔMES-01 — Vérification des offres en ligne contre les VRAIS sites (à lancer depuis le PC d'Alice).

Deux usages :

  1. Classer des URL précises (aucune base lue ni écrite) :
       py scripts\\verifier_offres_en_ligne.py --url "https://www.hellowork.com/fr-fr/emplois/85107847.html"
     La source est déduite du domaine (free-work.com / hellowork.com).

  2. Vérifier les offres à risque de la base, en SIMULATION par défaut (rien n'est écrit) :
       py scripts\\verifier_offres_en_ligne.py --db data\\offers.db --limite 10
     Ajouter --ecrire pour enregistrer les statuts (ce que fait l'étape 8 du pipeline).
     Toutes les offres à risque sont considérées « non revues pendant ce run ».

Même classement, même délai de politesse et même timeout que le pipeline (src/verification/en_ligne.py).
Aucune offre n'est jamais supprimée.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def source_depuis_url(url: str) -> str | None:
    hote = urlparse(url).netloc.lower()
    if hote.endswith("free-work.com"):
        return "Free-Work"
    if hote.endswith("hellowork.com"):
        return "HelloWork"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vérifier que des offres sont encore en ligne.")
    ap.add_argument("--url", action="append", default=[], help="URL d'offre à classer (répétable)")
    ap.add_argument("--db", help="base à utiliser (défaut : DB_PATH ou data/offers.db)")
    ap.add_argument("--limite", type=int, default=None, help="nombre maximal d'offres vérifiées")
    ap.add_argument("--ecrire", action="store_true", help="enregistrer les statuts en base (sinon simulation)")
    args = ap.parse_args(argv)

    if args.db:
        os.environ["DB_PATH"] = args.db
    os.chdir(ROOT)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from src.verification import en_ligne   # après DB_PATH

    if args.url:
        import requests
        session = requests.Session()
        session.headers.update(en_ligne.HEADERS)
        delais = en_ligne.delais_politesse()
        for url in args.url:
            source = source_depuis_url(url)
            if source is None:
                print(f"?           {url}  (domaine non vérifiable : ni free-work.com ni hellowork.com)")
                continue
            time.sleep(delais.get(source, en_ligne.DELAI_POLITESSE_DEFAUT))
            statut, detail = en_ligne.verifier_url(session, source, url)
            print(f"{statut.upper():<11} {source:<10} {url}\n            {detail}")
        return 0

    import yaml
    criteres = yaml.safe_load((ROOT / "config" / "criteria.yaml").read_text(encoding="utf-8"))
    score_min = criteres.get("seuils", {}).get("score_ia_minimum", 60)
    limite = args.limite or en_ligne.MAX_VERIFICATIONS_PAR_RUN
    print(f"Base : {os.environ.get('DB_PATH', 'data/offers.db')} — "
          f"{'ÉCRITURE des statuts' if args.ecrire else 'SIMULATION (rien n écrit)'} — limite {limite}")
    bilan = en_ligne.verifier_offres(datetime.now().isoformat(), score_min=score_min, limite=limite,
                                     ecrire=args.ecrire)
    print()
    for d in bilan["details"]:
        print(f"{d['statut'].upper():<11} {d['source']:<10} {(d['titre'] or '')[:55]:<55} {d['url']}\n            {d['detail']}")
    print(f"\nBilan : {bilan['verifiees']} vérifiée(s) — {bilan['en_ligne']} en ligne, "
          f"{bilan['hors_ligne']} hors ligne, {bilan['inconnu']} inconnue(s)"
          + (" — plafond atteint" if bilan["plafond_atteint"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
