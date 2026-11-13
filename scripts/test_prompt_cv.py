"""
CV-03 — Prompt de reformulation : sorties AVANT / APRÈS sur un même CV et une même annonce.

Appelle Haiku DEUX fois (une par version du prompt), avec les mêmes données :
  - un CV figé de 6 missions chez 6 employeurs différents ;
  - une annonce qui exige un sigle ABSENT du CV (« PES/DES ») ;
  - des instructions opérateur de test (ou les instructions par défaut lues en base, --db).

Affiche côte à côte : POINTS FORTS, COMPÉTENCES CLÉS, expériences mises en exergue,
et, pour chaque version, si un sigle de l'annonce absent du CV apparaît dans la réponse.

"AVANT" = src/cv_genere/reformulation.py tel qu'au commit --ref (lu via git show),
"APRÈS" = le fichier du répertoire de travail.

Aucune écriture en base (base ouverte en lecture seule), aucun PDF généré.
Clé API : variable d'environnement ANTHROPIC_API_KEY.

Usage (depuis la racine du dépôt) :
  py scripts/test_prompt_cv.py
  py scripts/test_prompt_cv.py --ref 27bca02 --db data\\offers.db
"""

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REF_AVANT = "27bca02"   # dernier commit avant CV-03
FICHIER = "src/cv_genere/reformulation.py"
LARGEUR_COL = 55

CV_TEXTE = """Business Analyst / AMOA senior — 14 ans d'expérience en banque et assurance.
Consultante orientée métier, habituée aux programmes de transformation, au recueil des besoins
et à la conduite du changement auprès des directions métiers.

EXPÉRIENCES PROFESSIONNELLES

BNP Paribas — Business Analyst Paiements (2022 – 2025)
- Recueil des besoins des métiers Cash Management pour la migration des virements SEPA vers la plateforme cible.
- Rédaction des spécifications fonctionnelles des flux SEPA SCT et SDD, et des règles de rejet.
- Pilotage de la recette : 600 cas de test, coordination de 4 équipes MOE, suivi des anomalies sous Jira.
- Animation des comités métier hebdomadaires et préparation des supports de décision.

Société Générale — AMOA Conformité (2019 – 2022)
- Cadrage du projet de contrôle des transactions au titre de la lutte anti-blanchiment (LCB-FT).
- Analyse des écarts entre le dispositif existant et les exigences réglementaires, plan de remédiation.
- Recette des scénarios d'alerte et accompagnement des équipes conformité.

AXA France — Chef de projet MOA (2016 – 2019)
- Pilotage de la refonte de l'outil de gestion des sinistres habitation, budget de 1,2 M€.
- Conduite du changement auprès de 300 gestionnaires : formation, guides utilisateurs, support au démarrage.
- Rédaction des expressions de besoin et arbitrage des priorités avec les métiers.

Crédit Agricole CIB — Business Analyst Trade Finance (2014 – 2016)
- Spécifications des évolutions de l'outil de lettres de crédit documentaires.
- Recette fonctionnelle et rédaction des procédures opérationnelles.

La Banque Postale — Analyste fonctionnelle (2012 – 2014)
- Modélisation des processus d'ouverture de compte en agence.
- Rédaction des cahiers de recette et exécution des tests.

Capgemini — Consultante junior (2011 – 2012)
- Support à la recette d'un progiciel de gestion de portefeuilles titres.

COMPÉTENCES : AMOA, Recueil du besoin, Spécifications fonctionnelles, Recette, Jira, SQL, SEPA,
Conduite du changement, Agile / Scrum, LCB-FT
FORMATION : Master Finance — Université Paris-Dauphine
LANGUES : Français (natif), Anglais (courant)
"""

CV = {
    "id": 0,
    "texte_brut": CV_TEXTE,
    "titre_courant": "Business Analyst / AMOA senior",
    "annees_experience": 14,
    "profil_adh": "",
    "notes_experiences": "",
    "competences_techniques": json.dumps([
        "AMOA", "Recueil du besoin", "Spécifications fonctionnelles", "Recette", "Jira", "SQL",
        "SEPA", "Conduite du changement", "Agile / Scrum", "LCB-FT"]),
    "domaines": json.dumps(["banque", "assurance", "paiements"]),
}

OFFRE = {
    "titre": "Business Analyst Paiements H/F",
    "entreprise": "Banque Exemple",
    "description": (
        "Au sein de la direction des paiements, vous intervenez sur le programme de modernisation "
        "des flux. Missions : recueil et formalisation des besoins des métiers paiements, rédaction "
        "des spécifications fonctionnelles des flux SEPA, pilotage de la recette et suivi des "
        "anomalies, animation des ateliers avec les métiers. Une connaissance des échanges de flux "
        "avec le Trésor public (PES/DES) est indispensable. Environnement agile. Anglais "
        "professionnel apprécié."
    ),
}

# Missions les plus proches de l'annonce (attendues en exergue et en points forts)
MISSIONS_PROCHES = ["BNP Paribas"]
EMPLOYEURS = ["BNP Paribas", "Société Générale", "AXA", "Crédit Agricole", "Banque Postale", "Capgemini"]

INSTRUCTIONS_TEST = (
    "Les points forts doivent être concrets et citer les clients.\n"
    "Ne jamais afficher un sigle ou un outil qui n'est pas dans le CV, même s'il est dans l'annonce."
)


# ── Chargement des deux versions du prompt ───────────────────────────────────

def charger_avant(ref: str):
    """Charge reformulation.py tel qu'au commit `ref`, comme module isolé."""
    try:
        source = subprocess.run(
            ["git", "show", f"{ref}:{FICHIER}"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except Exception as e:
        sys.exit(f"Impossible de lire la version AVANT ({ref}) via git : {e}")
    chemin = Path(tempfile.gettempdir()) / f"reformulation_avant_{ref}.py"
    chemin.write_text(source, encoding="utf-8")
    return _charger("reformulation_avant", chemin)


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Instructions par défaut lues en base (lecture seule) ─────────────────────

def instructions_en_base(db: Path) -> str | None:
    """cv_instructions_defaut si la table parametres existe et la valeur n'est pas vide."""
    try:
        conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
        row = conn.execute("SELECT valeur FROM parametres WHERE cle = 'cv_instructions_defaut'").fetchone()
        conn.close()
    except sqlite3.Error as e:
        print(f"  (instructions par défaut non lues dans {db} : {e})")
        return None
    return row[0] if row and (row[0] or "").strip() else None


# ── Analyse et affichage ─────────────────────────────────────────────────────

def sigles_absents_du_cv() -> list[str]:
    """Sigles (2+ majuscules) de l'annonce qui n'apparaissent pas dans le CV source."""
    sigles = set(re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", OFFRE["description"] + " " + OFFRE["titre"]))
    source = CV_TEXTE + " " + CV["competences_techniques"]
    return sorted(s for s in sigles if not re.search(rf"\b{re.escape(s)}\b", source))


def texte_visible(data: dict) -> str:
    champs = {k: data.get(k) for k in ("profil", "key_value_bullets", "competences_top6_ordonnees", "experiences")}
    return json.dumps(champs, ensure_ascii=False)


def colonnes(gauche: list[str], droite: list[str]) -> None:
    """Affiche deux listes côte à côte, chaque élément replié sur LARGEUR_COL."""
    def replier(items):
        lignes = []
        for item in items or ["(vide)"]:
            morceaux = textwrap.wrap(item, LARGEUR_COL - 2) or [""]
            lignes.append("- " + morceaux[0])
            lignes += ["  " + m for m in morceaux[1:]]
        return lignes
    g, d = replier(gauche), replier(droite)
    for i in range(max(len(g), len(d))):
        cg = g[i] if i < len(g) else ""
        cd = d[i] if i < len(d) else ""
        print(f"  {cg:<{LARGEUR_COL}} | {cd}")


def titre_section(t: str) -> None:
    print()
    print(f"── {t} " + "─" * max(0, 2 * LARGEUR_COL - len(t)))
    print(f"  {'AVANT':<{LARGEUR_COL}} | APRÈS")


def exergue(data: dict) -> list[str]:
    return [f"{e.get('entreprise')} — {e.get('intitule')}"
            for e in data.get("experiences") or [] if e.get("a_mettre_en_avant")]


def employeurs_cites(bullets: list[str]) -> list[str]:
    txt = " ".join(bullets or []).lower()
    return [e for e in EMPLOYEURS if e.lower() in txt]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=REF_AVANT, help="commit de la version AVANT du prompt")
    ap.add_argument("--db", default=None,
                    help="base (lecture seule) pour utiliser les instructions par défaut enregistrées")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY n'est pas définie dans cette fenêtre : aucun appel effectué.")

    instructions, origine = INSTRUCTIONS_TEST, "instructions de test du script"
    if args.db:
        db = Path(args.db)
        if not db.exists():
            sys.exit(f"Base introuvable : {db}")
        en_base = instructions_en_base(db)
        if en_base:
            instructions, origine = en_base, f"instructions par défaut lues dans {db} (lecture seule)"
        else:
            origine += f" (aucune instruction par défaut enregistrée dans {db})"

    avant = charger_avant(args.ref)
    apres = _charger("reformulation_apres", ROOT / FICHIER)
    sigles = sigles_absents_du_cv()

    print("=" * (2 * LARGEUR_COL + 5))
    print(f"CV-03 — AVANT = {FICHIER} @ {args.ref} | APRÈS = répertoire de travail")
    print(f"Modèle : {apres.MODELE} (température 0)")
    print(f"Annonce : {OFFRE['titre']} — sigles absents du CV : {', '.join(sigles) or 'aucun'}")
    print(f"Instructions opérateur : {origine}")
    for ligne in instructions.splitlines():
        print(f"    > {ligne}")
    print("=" * (2 * LARGEUR_COL + 5))

    resultats = {}
    for nom, module in (("AVANT", avant), ("APRÈS", apres)):
        print(f"Appel Haiku — version {nom}…", flush=True)
        try:
            resultats[nom] = module.reformuler_avec_haiku(dict(CV), dict(OFFRE), "fr", instructions)
        except Exception as e:
            sys.exit(f"Échec de l'appel Haiku (version {nom}) : {e}")
    a, p = resultats["AVANT"], resultats["APRÈS"]

    titre_section("POINTS FORTS")
    colonnes(a.get("key_value_bullets"), p.get("key_value_bullets"))
    titre_section("COMPÉTENCES CLÉS (dans l'ordre)")
    colonnes(a.get("competences_top6_ordonnees"), p.get("competences_top6_ordonnees"))
    titre_section("EXPÉRIENCES MISES EN EXERGUE")
    colonnes(exergue(a), exergue(p))

    print()
    print("── CONTRÔLES " + "─" * (2 * LARGEUR_COL - 8))
    for nom, data in (("AVANT", a), ("APRÈS", p)):
        visible = texte_visible(data)
        trouves = [s for s in sigles if re.search(rf"\b{re.escape(s)}\b", visible)]
        etat = "OUI — " + ", ".join(trouves) if trouves else "non"
        print(f"  {nom:<6} sigle de l'annonce absent du CV présent dans la réponse : {etat}")
    for nom, data in (("AVANT", a), ("APRÈS", p)):
        cites = employeurs_cites(data.get("key_value_bullets"))
        print(f"  {nom:<6} employeurs nommés dans les points forts : {', '.join(cites) or 'aucun'}")
    for nom, data in (("AVANT", a), ("APRÈS", p)):
        ex = " ".join(exergue(data))
        ok = all(m in ex for m in MISSIONS_PROCHES)
        print(f"  {nom:<6} mission la plus proche ({', '.join(MISSIONS_PROCHES)}) en exergue : {'oui' if ok else 'NON'}")
    print()
    print("Aucune écriture en base, aucun PDF généré.")


if __name__ == "__main__":
    main()
