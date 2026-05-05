"""
Script de non-régression — pré-filtre keyword_filter.

Vérifie que la logique de filtrage se comporte comme attendu sur
des cas représentatifs. Lance avec : python scripts/test_prefilter.py

Familles testées :
  - PROFIL     : au moins 1 mot requis dans titre+description
  - SECTEUR    : au moins 1 mot sectoriel dans titre+description
  - EXCLUSION  : mot exclu dans le TITRE seulement (pas description)
  - SCORE      : score minimum atteint
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.filters.keyword_filter import _normaliser_texte, _normaliser_titre, _contient, evaluer

config_path = Path(__file__).parent.parent / "config" / "criteria.yaml"
with open(config_path, encoding="utf-8") as f:
    criteres = yaml.safe_load(f)

sectoriels_liste = [m.lower() for m in criteres.get("mots_cles", {}).get("sectoriels", [])]

SEP = "─" * 72

# ── Définition des cas ────────────────────────────────────────────────────────
# Format : (label, offre_dict, attendu_ok, raison_attendue_si_rejet)
# raison_attendue_si_rejet : sous-chaîne attendue dans la raison, ou None si accepté.

CAS = [
    # ── DOIT ÊTRE ACCEPTÉ ─────────────────────────────────────────────────────
    (
        "ACCEPT | profil+secteur dans titre",
        {
            "titre": "Chef de projet bancaire CDI",
            "description": "Poste en CDI au sein d'une banque retail.",
            "entreprise": "BNP Paribas",
            "source": "APEC",
        },
        True, None,
    ),
    (
        "ACCEPT | secteur (banque) dans titre, profil (BA) dans titre",
        {
            "titre": "Business Analyst / PO Banque H/F",
            "description": "Au sein d'une équipe de 10 personnes.",
            "entreprise": "Test SA",
            "source": "Welcome to the Jungle",
        },
        True, None,
    ),
    (
        "ACCEPT | profil (MOA) + secteur (assurance) dans titre",
        {
            "titre": "MOA – Projets Assurance Vie",
            "description": "Transformation digitale d'un assureur vie.",
            "entreprise": "AXA",
            "source": "Free-Work",
        },
        True, None,
    ),
    (
        "ACCEPT | secteur dans description uniquement (portefeuille, banque)",
        {
            "titre": "Chef de projet SI",
            "description": "Poste en banque de détail, gestion de portefeuille client.",
            "entreprise": "Crédit Agricole",
            "source": "APEC",
        },
        True, None,
    ),
    (
        "ACCEPT | 'alternance' dans DESCRIPTION seulement → ne doit PAS rejeter",
        {
            "titre": "Business Analyst senior – secteur finance",
            "description": "Une alternance est possible pour profils juniors. CDI ou freelance.",
            "entreprise": "Deloitte",
            "source": "Welcome to the Jungle",
        },
        True, None,
    ),
    # ── DOIT ÊTRE REJETÉ ──────────────────────────────────────────────────────
    (
        "REJECT | exclusion : 'développeur' dans titre",
        {
            "titre": "Développeur backend senior",
            "description": "Startup fintech, rejoignez notre équipe tech.",
            "entreprise": "Startup XYZ",
            "source": "Indeed",
        },
        False, "mot-clé exclusion",
    ),
    (
        "REJECT | exclusion : 'stage' dans titre (même si banque présente)",
        {
            "titre": "Stage chef de projet en banque",
            "description": "Stage de 6 mois au sein d'une banque.",
            "entreprise": "BNP Paribas",
            "source": "APEC",
        },
        False, "mot-clé exclusion",
    ),
    (
        "REJECT | exclusion : 'alternance' dans titre",
        {
            "titre": "Alternance Business Analyst Finance",
            "description": "Contrat d'alternance de 2 ans en banque.",
            "entreprise": "La Banque Postale",
            "source": "APEC",
        },
        False, "mot-clé exclusion",
    ),
    (
        "ACCEPT | nouveaux termes : cash management + monétique (ajout mai 2026)",
        {
            "titre": "Business Analyst Cash Management H/F",
            "description": "Mission au sein du département monétique d'une grande banque.",
            "entreprise": "Test SA",
            "source": "Welcome to the Jungle",
        },
        True, None,
    ),
    (
        # Cas : profil OK mais secteur absent dans titre ET description
        # → doit être rejeté avec la raison "aucun secteur détecté"
        "REJECT | aucun secteur : titre et description sans vocabulaire financier",
        {
            "titre": "Business Analyst – Transformation Digitale",
            "description": "Poste au sein d'un cabinet de conseil généraliste.",
            "entreprise": "Cabinet Conseil",
            "source": "APEC",
        },
        False, "aucun secteur",
    ),
    (
        # Cas : profil OK avec secteur clairement non-financier (industrie)
        # → piège : si "industriel" est ajouté par erreur dans sectoriels, ce cas le détectera
        "REJECT | aucun secteur : contexte industriel non financier",
        {
            "titre": "Chef de projet déploiement industriel",
            "description": "Coordination du déploiement d'usines en Asie.",
            "entreprise": "Industries SA",
            "source": "LinkedIn",
        },
        False, "aucun secteur",
    ),
    (
        "REJECT | aucun secteur : profil ok, contexte e-commerce non financier",
        {
            "titre": "Chef de projet IT e-commerce",
            "description": "Digitalisation du parcours client retail. Gestion de backlog.",
            "entreprise": "Retail Corp",
            "source": "LinkedIn",
        },
        False, "aucun secteur",
    ),
    (
        "REJECT | aucun profil : rôle technique sans mot-clé profil",
        {
            "titre": "Architecte solution cloud",
            "description": "Définition de l'architecture SI pour une banque d'investissement.",
            "entreprise": "BNP Paribas",
            "source": "APEC",
        },
        False, "aucun mot-clé profil",
    ),
]

# ── Exécution ─────────────────────────────────────────────────────────────────
nb_ok = 0
nb_ko = 0

for label, offre, attendu_ok, raison_attendue in CAS:
    titre_norm = _normaliser_titre(offre.get("titre", ""))
    texte_complet = _normaliser_texte(
        f"{titre_norm} {offre.get('description', '')} {offre.get('entreprise', '')}"
    )
    sectoriels_matches = [m for m in sectoriels_liste if _contient(texte_complet, m)]

    ok, score, raison = evaluer(offre, criteres)

    # Évaluation du résultat
    if ok == attendu_ok:
        if not ok and raison_attendue and raison_attendue not in raison:
            verdict = "WARN"  # Rejeté pour la bonne décision mais pas la bonne raison
        else:
            verdict = "PASS"
            nb_ok += 1
    else:
        verdict = "FAIL"
        nb_ko += 1

    print(SEP)
    print(f"[{verdict}] {label}")
    print(f"  Titre brut  : {offre['titre']}")
    print(f"  Titre normé : {titre_norm}")
    print(f"  Résultat    : {'ACCEPTÉ (score=' + str(score) + ')' if ok else 'REJETÉ — ' + raison}")
    attendu_str = "ACCEPTÉ" if attendu_ok else f"REJETÉ ({raison_attendue or '?'}...)"
    print(f"  Attendu     : {attendu_str}")
    print(f"  Sectoriels matchés : {sectoriels_matches if sectoriels_matches else '(aucun)'}")
    if verdict != "PASS":
        print(f"  texte_complet : {texte_complet[:150]}...")

print(SEP)
print(f"\nRÉSUMÉ : {nb_ok}/{nb_ok + nb_ko} cas passés — {nb_ko} ÉCHEC(S)")
if nb_ko > 0:
    print("→ Des corrections sont nécessaires avant tout commit sur criteria.yaml.")
else:
    print("→ Tous les cas passent. Le filtre se comporte comme attendu.")
print()
