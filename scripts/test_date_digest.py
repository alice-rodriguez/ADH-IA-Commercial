"""
HYGIÈNE C — Test HORS RÉSEAU : date de l'en-tête du digest en français, locale système anglaise.

Force la locale anglaise (LC_TIME = en_US.UTF-8 si elle est installée, sinon C/POSIX, dont
les noms de jours et de mois sont anglais), montre que l'ancien format strftime("%A %d %B %Y")
sort en anglais, puis vérifie la date produite par le digest.

Usage (depuis la racine du dépôt) : python scripts/test_date_digest.py [fichier_sortie.html]
"""

import locale
import os
import re
import sys
from datetime import datetime
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.email_digest import digest   # noqa: E402

ECHECS = []


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


def forcer_locale_anglaise() -> str:
    for nom in ("en_US.UTF-8", "en_GB.UTF-8", "English_United States.1252", "C"):
        try:
            locale.setlocale(locale.LC_TIME, nom)
            return nom
        except locale.Error:
            continue
    return locale.setlocale(locale.LC_TIME)


def main():
    nom = forcer_locale_anglaise()
    d = datetime(2026, 11, 18, 9, 0)
    ancien = d.strftime("%A %d %B %Y").capitalize()
    print(f"Locale LC_TIME forcée : {nom}")
    print(f"  ancien format (strftime) : {ancien}")
    verifier("la locale forcée est bien anglaise (l'ancien format sort en anglais)", ancien == "Wednesday 18 november 2026")

    print("\nDate produite par le digest :")
    cas = {
        datetime(2026, 11, 18): "Mercredi 18 novembre 2026",
        datetime(2026, 11, 1): "Dimanche 1er novembre 2026",
        datetime(2026, 2, 9): "Lundi 9 février 2026",
        datetime(2026, 8, 15): "Samedi 15 août 2026",
        datetime(2026, 12, 31): "Jeudi 31 décembre 2026",
        datetime(2027, 1, 5): "Mardi 5 janvier 2027",
        datetime(2026, 7, 3): "Vendredi 3 juillet 2026",
    }
    for jour, attendu in cas.items():
        obtenu = digest.date_longue_fr(jour)
        print(f"  {jour:%Y-%m-%d} → {obtenu}")
        verifier(f"{attendu}", obtenu == attendu)

    html = digest.generer_html([], {}, {"collectees": 0, "dedup": 0, "passe1": 0, "passe2": 0}, 0.0, [])
    date_html = digest.date_longue_fr(datetime.now())
    entete = re.search(r'font-size:14px;margin-top:4px;">([^<]+)</div>', html)
    print(f"\nEn-tête du mail généré aujourd'hui : {entete.group(1) if entete else '(introuvable)'}")
    verifier("en-tête et titre du mail en français, aucun nom anglais",
             entete is not None and entete.group(1) == date_html and f"Digest {date_html}" in html
             and not re.search(r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|"
                               r"March|April|June|July|August|September|October|November|December", html))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(html, encoding="utf-8")
        print(f"HTML écrit dans {sys.argv[1]}")


if __name__ == "__main__":
    main()
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    sys.exit(1 if ECHECS else 0)
