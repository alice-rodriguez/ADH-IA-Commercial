"""
Script de test isolé — BOAMP uniquement.
Lance uniquement le collecteur BOAMP et affiche les résultats.
Utilisation : python test_boamp.py
"""

import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.collectors.boamp import BoampCollector

config_source = {
    "nom": "BOAMP",
    "delai_secondes": 1,
}
criteres = {
    "profils": ["chef de projet", "business analyst", "MOA"],
    "secteurs": ["banque", "assurance", "finance"],
}

print("\n" + "=" * 60)
print("TEST COLLECTEUR BOAMP")
print("=" * 60)

collector = BoampCollector(config_source)
try:
    offres = collector.collecter(criteres)
except Exception as e:
    print(f"\n✗ ERREUR : {e}")
    sys.exit(1)

print(f"\n✓ {len(offres)} offre(s) récupérée(s)\n")

if offres:
    print("─" * 60)
    print("EXEMPLE — Première offre :")
    print("─" * 60)
    print(json.dumps(offres[0], ensure_ascii=False, indent=2))
    if len(offres) > 1:
        print(f"\n... et {len(offres) - 1} autre(s) offre(s)")
else:
    print("Aucune offre retournée — vérifiez les logs ci-dessus.")
