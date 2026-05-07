"""
Tests unitaires pour src/utils/parsing.py.
Lance avec : python tests/test_parsing.py

Format identique à scripts/test_prefilter.py.
44 cas : 25 pour parse_tjm, 19 pour parse_salaire.

Contrat strict appliqué depuis mai 2026 :
  - parse_tjm  : signal obligatoire (préfixe ou suffixe journalier)
  - parse_salaire : signal obligatoire (k/K, préfixe salaire, ou suffixe annuel)
  - Sans signal → (None, None) dans les deux cas
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.parsing import parse_tjm, parse_salaire

SEP = "─" * 72

# Format : (label, fonction, entrée, résultat_attendu)
CAS: list[tuple] = [

    # ── parse_tjm — cas existants adaptés au contrat strict ──────────────────

    # Sans signal explicite → (None, None)
    ("TJM | valeur seule sans signal → (None, None)",
     parse_tjm, "450 €", (None, None)),

    ("TJM | plage sans espaces autour du tiret, sans signal → (None, None)",
     parse_tjm, "450-900 €", (None, None)),

    ("TJM | plage avec espaces autour du tiret, sans signal → (None, None)",
     parse_tjm, "450 - 900 €", (None, None)),

    ("TJM | plage sans espace avant €, sans signal → (None, None)",
     parse_tjm, "450-900€", (None, None)),

    # Suffixe journalier — signal présent → valeur extraite
    ("TJM | suffixe /j",
     parse_tjm, "450€/j", (450, 450)),

    ("TJM | suffixe /jour",
     parse_tjm, "450 €/jour", (450, 450)),

    # Préfixe TJM — signal présent → valeur extraite
    ("TJM | préfixe 'TJM :'",
     parse_tjm, "TJM : 500 €", (500, 500)),

    ("TJM | préfixe 'TJM' sans deux-points + plage",
     parse_tjm, "TJM 450-900 €", (450, 900)),

    ("TJM | préfixe 'TJM :' + plage + /jour",
     parse_tjm, "TJM : 1200 - 1800 €/jour", (1200, 1800)),

    # Espace insécable seul, sans signal → (None, None)
    ("TJM | espace insécable avant € (\\xa0), sans signal → (None, None)",
     parse_tjm, "450\xa0€", (None, None)),

    # Format k — c'est un salaire, pas un TJM
    ("TJM | format k → (None, None) : signal salaire, pas TJM",
     parse_tjm, "65k-70k €", (None, None)),

    # Cas limites
    ("TJM | texte vide → (None, None)",
     parse_tjm, "", (None, None)),

    ("TJM | None → (None, None)",
     parse_tjm, None, (None, None)),

    ("TJM | hors plage haut : 5000 > 2000, sans signal → (None, None)",
     parse_tjm, "5000 €", (None, None)),

    ("TJM | hors plage bas : 50 < 100, sans signal → (None, None)",
     parse_tjm, "50 €", (None, None)),

    ("TJM | min > max → rejeté",
     parse_tjm, "900-450 €", (None, None)),

    # ── parse_tjm — cas du diagnostic (faux positifs corrigés) ───────────────

    ("TJM | faux positif corrigé — /mois n'est pas un signal TJM",
     parse_tjm, "Mission ponctuelle, 1 500 €/mois", (None, None)),

    ("TJM | faux positif corrigé — montant seul sans contexte journalier",
     parse_tjm, "Budget : 800 €", (None, None)),

    # ── parse_tjm — cas-piège supplémentaires ────────────────────────────────

    ("TJM | piège — /an est un signal salaire, pas TJM",
     parse_tjm, "900 €/an", (None, None)),

    ("TJM | piège — suffixe /day reconnu comme TJM",
     parse_tjm, "650 €/day", (650, 650)),

    ("TJM | piège — préfixe 'rate' reconnu comme TJM",
     parse_tjm, "Rate: 750 €", (750, 750)),

    ("TJM | piège — hors plage haut AVEC signal → rejeté par plage",
     parse_tjm, "TJM : 5000 €", (None, None)),

    # ── parse_salaire — cas existants adaptés au contrat strict ──────────────

    # Format k/K — signal intrinsèque suffisant
    ("SAL | valeur simple avec k minuscule",
     parse_salaire, "65k €", (65000, 65000)),

    ("SAL | plage avec k minuscule",
     parse_salaire, "65k-70k €", (65000, 70000)),

    ("SAL | plage avec K majuscule + sans espace avant €",
     parse_salaire, "65K-70K€", (65000, 70000)),

    ("SAL | plage avec k et espaces variés",
     parse_salaire, "65 k - 70 k €", (65000, 70000)),

    # Grand nombre sans signal explicite → (None, None)
    ("SAL | grand nombre avec espace français, sans signal → (None, None)",
     parse_salaire, "45 000 €", (None, None)),

    ("SAL | grand nombre sans espace, sans signal → (None, None)",
     parse_salaire, "45000 €", (None, None)),

    ("SAL | plage grands nombres, sans signal → (None, None)",
     parse_salaire, "45000-65000 €", (None, None)),

    # Préfixe salaire — signal présent
    ("SAL | préfixe 'Salaire :' sans signe €",
     parse_salaire, "Salaire : 65k", (65000, 65000)),

    # Espace insécable seul, sans signal → (None, None)
    ("SAL | espaces insécables (45\\xa0000\\xa0€), sans signal → (None, None)",
     parse_salaire, "45\xa0000\xa0€", (None, None)),

    # Valeur typique TJM → trop petite pour un salaire et sans signal annuel
    ("SAL | format TJM → (None, None) : pas de signal salaire",
     parse_salaire, "450-900 €", (None, None)),

    # Hors plage
    ("SAL | hors plage bas : 5k = 5 000 < 15 000",
     parse_salaire, "5k €", (None, None)),

    ("SAL | hors plage haut : 500k = 500 000 > 300 000",
     parse_salaire, "500k €", (None, None)),

    # ── parse_salaire — cas du diagnostic (faux positifs corrigés) ───────────

    ("SAL | faux positif corrigé — grand nombre sans signal salaire",
     parse_salaire, "45 000 € de chiffre d'affaires", (None, None)),

    ("SAL | faux positif corrigé — 'brut' seul n'est pas un signal annuel",
     parse_salaire, "Indemnité de 20 000 € brut", (None, None)),

    # ── parse_salaire — cas-piège supplémentaires ─────────────────────────────

    ("SAL | piège — /jour est un signal TJM, pas salaire",
     parse_salaire, "450 €/jour", (None, None)),

    ("SAL | piège — préfixe 'package' reconnu comme signal salaire",
     parse_salaire, "Package 70000 €", (70000, 70000)),

    # ── parse_tjm — cas-positifs validant la nouvelle logique ─────────────────

    ("TJM | nouveau positif — préfixe 'tarif journalier'",
     parse_tjm, "tarif journalier : 550 €", (550, 550)),

    ("TJM | nouveau positif — préfixe 'taux journalier' + plage",
     parse_tjm, "taux journalier 700-850 €", (700, 850)),

    ("TJM | nouveau positif — suffixe HT/j",
     parse_tjm, "600 € HT/j", (600, 600)),

    # ── parse_salaire — cas-positifs validant la nouvelle logique ─────────────

    ("SAL | nouveau positif — préfixe 'Rémunération' + grand nombre",
     parse_salaire, "Rémunération : 75000 €", (75000, 75000)),

    ("SAL | nouveau positif — suffixe /an",
     parse_salaire, "60000 €/an", (60000, 60000)),

    ("SAL | nouveau positif — suffixe 'brut annuel' + plage",
     parse_salaire, "45000 - 55000 € brut annuel", (45000, 55000)),
]

nb_ok = 0
nb_ko = 0

for label, fn, entree, attendu in CAS:
    resultat = fn(entree)
    verdict = "PASS" if resultat == attendu else "FAIL"
    if verdict == "PASS":
        nb_ok += 1
    else:
        nb_ko += 1

    entree_affiche = repr(entree) if entree is not None else "None"
    print(SEP)
    print(f"[{verdict}] {label}")
    print(f"  Entrée   : {entree_affiche}")
    print(f"  Attendu  : {attendu}")
    print(f"  Obtenu   : {resultat}")

print(SEP)
print(f"\nRÉSUMÉ : {nb_ok}/{nb_ok + nb_ko} cas passés — {nb_ko} ÉCHEC(S)")
if nb_ko > 0:
    print("→ Des corrections sont nécessaires.")
    sys.exit(1)
else:
    print("→ Tous les cas passent.")
