"""Tests standalone du module matching (CV.3.A).

Usage : python tests/test_matching.py
"""

import sys
sys.path.insert(0, ".")

from src.matching.utils import normaliser, extraire_annees_requises, lieu_proche
from src.matching.scoring import (
    score_competences,
    score_domaine,
    score_experience,
    score_contrat,
    calculer_score_global,
)

_fails = 0
_ok = 0


def check(label: str, actual, expected):
    global _fails, _ok
    if actual != expected:
        print(f"[FAIL] {label} : attendu {expected!r}, obtenu {actual!r}")
        _fails += 1
    else:
        _ok += 1


def check_range(label: str, actual, lo, hi):
    global _fails, _ok
    if not (lo <= actual <= hi):
        print(f"[FAIL] {label} : {actual!r} hors de [{lo}, {hi}]")
        _fails += 1
    else:
        _ok += 1


def main():
    # ── normaliser ──────────────────────────────────────────────────────────
    check("normaliser minuscules",          normaliser("Python"),            "python")
    check("normaliser accents",             normaliser("expérience"),        "experience")
    check("normaliser tiret supprimé",      normaliser("S/4HANA"),           "s4hana")
    check("normaliser slash supprimé",      normaliser("AWS/GCP"),           "awsgcp")
    check("normaliser espaces normalisés",  normaliser("  ile  de  france  "), "ile de france")

    # ── extraire_annees_requises ─────────────────────────────────────────────
    check("annees simple",      extraire_annees_requises("5 ans d'expérience minimum"), 5)
    check("annees fourchette",  extraire_annees_requises("3 à 5 ans d'experience requis"), 3)
    check("annees aucune",      extraire_annees_requises("Poste ouvert à tous profils"), None)
    check("annees minimum",     extraire_annees_requises("Minimum 7 ans d'expérience"), 7)

    # ── lieu_proche ──────────────────────────────────────────────────────────
    check("lieu identique",     lieu_proche("Paris", "Paris"),                        100)
    check("lieu IDF/IDF",       lieu_proche("Boulogne-Billancourt", "Neuilly-sur-Seine"), 75)
    check("lieu remote offre",  lieu_proche("Lyon", "Remote / Télétravail"),           100)
    check("lieu sans lien",     lieu_proche("Bordeaux", "Lille"),                       0)
    check("lieu cv vide",       lieu_proche("", "Paris"),                              50)

    # ── score_competences ───────────────────────────────────────────────────
    check("competences toutes",  score_competences(["Python", "SQL", "AWS"], "Poste Python SQL AWS cloud"), 100)
    check("competences aucune",  score_competences(["COBOL", "FORTRAN"], "Développeur Python junior"),       0)
    check("competences moitié",  score_competences(["Python", "Java"], "Expertise Python requise"),         50)

    # ── score_domaine ───────────────────────────────────────────────────────
    check("domaine vide neutre",  score_domaine([], "Mission banque finance"),           50)
    check_range("domaine présent", score_domaine(["banque", "finance"], "secteur bancaire et finance"), 1, 100)
    check("domaine absent",       score_domaine(["santé"], "Mission pour opérateur télécom"), 0)

    # ── score_experience ────────────────────────────────────────────────────
    check("experience suffisante",  score_experience(8, "5 ans d'expérience minimum"), 100)
    check("experience insuffisante", score_experience(2, "5 ans d'expérience minimum"), 40)
    check("experience inconnue",    score_experience(None, "5 ans d'expérience"),        50)
    check("experience pas requis",  score_experience(3, "Poste ouvert à tous"),          75)

    # ── score_contrat ────────────────────────────────────────────────────────
    check("contrat cv ouvert",  score_contrat([], "CDI"),               100)
    check("contrat match",      score_contrat(["Freelance"], "Mission Freelance"), 100)
    check("contrat no match",   score_contrat(["CDI"], "Mission Freelance"),         0)

    # ── calculer_score_global ────────────────────────────────────────────────
    cv = {
        "competences_techniques": '["Python", "SQL"]',
        "domaines": '["banque"]',
        "annees_experience": 5,
        "types_contrat_souhaites": '["Freelance"]',
        "localisation_preferee": "Paris",
    }
    offre = {
        "titre": "Data Engineer Python SQL",
        "description": "Mission dans la banque, 3 ans d'expérience minimum, Freelance, Paris",
        "resume_ia": "",
        "lieu": "Paris",
        "type_contrat": "Freelance",
        "type_contrat_clarifie": "Freelance",
    }
    result = calculer_score_global(cv, offre)
    check_range("score_global dans [0,100]", result["score_global"], 0, 100)
    check("details_json présent",            "details_json" in result,       True)

    # ── postes_cibles boost ──────────────────────────────────────────────────
    # CV avec compétences partielles (1/3 matchée) + postes_cibles qui matche
    cv_avec_postes = {
        "competences_techniques": '["Python", "Java", "C++"]',
        "domaines": '[]',
        "annees_experience": None,
        "types_contrat_souhaites": '[]',
        "localisation_preferee": None,
        "postes_cibles": "Directeur de programme SAP",
    }
    cv_sans_postes = {
        "competences_techniques": '["Python", "Java", "C++"]',
        "domaines": '[]',
        "annees_experience": None,
        "types_contrat_souhaites": '[]',
        "localisation_preferee": None,
    }
    offre_postes = {
        "titre": "Directeur de programme SAP banque",
        "description": "Mission Python requis",
        "resume_ia": "",
        "lieu": "Paris",
        "type_contrat": "Freelance",
        "type_contrat_clarifie": "Freelance",
    }
    r_avec = calculer_score_global(cv_avec_postes, offre_postes)
    r_sans = calculer_score_global(cv_sans_postes, offre_postes)
    check("boost postes_cibles : score_competences boosté de +25",
          r_avec["score_competences"] - r_sans["score_competences"], 25)

    # ── lieu + contrat à 0% : bon score même si mismatch ────────────────────
    cv_geo_contrat_ko = {
        "competences_techniques": '["Python", "SQL", "Data"]',
        "domaines": '["banque"]',
        "annees_experience": 5,
        "types_contrat_souhaites": '["CDI"]',
        "localisation_preferee": "Bordeaux",
    }
    offre_geo_contrat_ko = {
        "titre": "Data Analyst Python SQL banque",
        "description": "secteur bancaire 3 ans d'expérience Paris",
        "resume_ia": "",
        "lieu": "Paris",
        "type_contrat": "Freelance",
        "type_contrat_clarifie": "Freelance",
    }
    r_geo = calculer_score_global(cv_geo_contrat_ko, offre_geo_contrat_ko)
    check("lieu+contrat 0poids : score_lieu hors-match calculé", r_geo["score_lieu"], 0)
    check("lieu+contrat 0poids : score_contrat hors-match calculé", r_geo["score_contrat"], 0)
    check_range("lieu+contrat 0poids : score_global élevé malgré mismatch",
                r_geo["score_global"], 80, 100)

    # ── details_json contient postes_cibles_trouves ──────────────────────────
    import json as _json
    cv_pc = {
        "competences_techniques": '["Python"]',
        "domaines": '[]',
        "annees_experience": None,
        "types_contrat_souhaites": '[]',
        "localisation_preferee": None,
        "postes_cibles": "Directeur de programme SAP, Chef de projet",
    }
    offre_pc = {
        "titre": "Chef de projet IT",
        "description": "Mission chef de projet Paris",
        "resume_ia": "",
        "lieu": "Paris",
        "type_contrat": "Freelance",
        "type_contrat_clarifie": "Freelance",
    }
    r_pc = calculer_score_global(cv_pc, offre_pc)
    details_pc = _json.loads(r_pc["details_json"])
    check("details_json : postes_cibles_trouves présent",
          "postes_cibles_trouves" in details_pc, True)
    check("details_json : Chef de projet trouvé",
          "Chef de projet" in details_pc.get("postes_cibles_trouves", []), True)

    # ── Résumé ───────────────────────────────────────────────────────────────
    total = _ok + _fails
    if _fails == 0:
        print(f"[OK] {total} tests passés")
    else:
        print(f"[RÉSUMÉ] {_ok}/{total} OK, {_fails} FAIL(S)")
        sys.exit(1)


if __name__ == "__main__":
    main()
