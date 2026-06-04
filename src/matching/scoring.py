"""Fonctions de scoring pour le matching CVs ↔ offres.

Pondération globale (CV.2.bis.3.bis) :
  Compétences  60 %
  Domaine      25 %
  Expérience   15 %
  Lieu          0 % (calculé + stocké dans details_json, hors score global)
  Contrat       0 % (idem)
"""

import json
import logging
from typing import Optional

from src.matching.utils import (
    SYNONYMES_COMPETENCES,
    VARIANTES_DOMAINES,
    _domaines_cv_normalises,
    extraire_annees_requises,
    lieu_proche,
    normaliser,
)

logger = logging.getLogger(__name__)

POIDS = {
    "competences": 0.60,
    "domaine":     0.25,
    "experience":  0.15,
    "contrat":     0.00,   # gardé pour traçabilité, hors score global
    "lieu":        0.00,   # idem
}


# ---------------------------------------------------------------------------
# Scores individuels (retournent un entier 0–100)
# ---------------------------------------------------------------------------


def score_competences(competences_cv: list[str], texte_offre: str) -> int:
    """Proportion de compétences du CV trouvées dans le texte de l'offre.

    Pour chaque compétence, la correspondance est vérifiée sur :
    - la forme normalisée de la compétence elle-même
    - + tous ses synonymes issus de SYNONYMES_COMPETENCES
    Une compétence est matchée si AU MOINS UN des termes est présent.
    """
    if not competences_cv or not texte_offre:
        return 0
    texte_norm = normaliser(texte_offre)
    trouvees = 0
    for c in competences_cv:
        c_norm = normaliser(c)
        # Correspondance directe
        if c_norm in texte_norm:
            trouvees += 1
            continue
        # Synonymes : lookup insensible à la casse via la clé originale
        synonymes = SYNONYMES_COMPETENCES.get(c) or SYNONYMES_COMPETENCES.get(c.title()) or []
        if any(s in texte_norm for s in synonymes):
            trouvees += 1
    return round(100 * trouvees / len(competences_cv))


def score_domaine(domaines_cv: list[str], texte_offre: str) -> int:
    """Correspondance des domaines métier entre CV et offre.

    Si le CV n'a pas de domaine renseigné → 50 (neutre).
    """
    if not domaines_cv:
        return 50
    if not texte_offre:
        return 0

    texte_norm = normaliser(texte_offre)
    couvertes_cv = _domaines_cv_normalises(domaines_cv)

    if not couvertes_cv:
        return 50

    correspondances = 0
    for cle in couvertes_cv:
        for variante in VARIANTES_DOMAINES[cle]:
            if variante in texte_norm:
                correspondances += 1
                break

    return round(100 * correspondances / len(couvertes_cv))


def score_experience(annees_cv: Optional[int], texte_offre: str) -> int:
    """Adéquation entre l'expérience du CV et celle requise dans l'offre.

    Si l'expérience CV est inconnue → 50 (neutre).
    Si l'offre ne précise pas → 75 (pas de barrière).
    """
    if annees_cv is None:
        return 50
    annees_requises = extraire_annees_requises(texte_offre)
    if annees_requises is None:
        return 75
    if annees_cv >= annees_requises:
        return 100
    ratio = annees_cv / annees_requises
    return round(100 * ratio)


def score_contrat(types_cv: list[str], type_offre: Optional[str]) -> int:
    """Correspondance type de contrat.

    CV sans préférence (liste vide) → 100 (ouvert à tout).
    Offre sans type → 75.
    """
    if not types_cv:
        return 100
    if not type_offre:
        return 75

    type_offre_norm = normaliser(type_offre)
    for t in types_cv:
        t_norm = normaliser(t)
        if t_norm in type_offre_norm or type_offre_norm in t_norm:
            return 100
        # Correspondances sémantiques fréquentes
        if t_norm in ("freelance", "independant") and any(
            k in type_offre_norm for k in ("freelance", "independant", "mission")
        ):
            return 100
        if t_norm == "cdi" and "cdi" in type_offre_norm:
            return 100
        if t_norm == "cdd" and "cdd" in type_offre_norm:
            return 100
    return 0


def score_lieu(lieu_cv: Optional[str], lieu_offre: Optional[str]) -> int:
    """Délègue à lieu_proche() (0 / 50 / 75 / 100)."""
    return lieu_proche(lieu_cv or "", lieu_offre or "")


# ---------------------------------------------------------------------------
# Score global
# ---------------------------------------------------------------------------


def calculer_score_global(cv: dict, offre: dict) -> dict:
    """Calcule tous les scores pour un couple (CV, offre).

    Args:
        cv: dict avec clés issues de la table cvs (JSON dans competences_techniques,
            domaines, types_contrat_souhaites).
        offre: dict avec clés issues de la table offres.

    Returns:
        Dict avec score_global, score_competences, score_domaine,
        score_experience, score_contrat, score_lieu, details_json.
    """
    def _parse_json_list(val) -> list:
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val) or []
        except (json.JSONDecodeError, TypeError):
            return []

    competences_cv = _parse_json_list(cv.get("competences_techniques"))
    domaines_cv = _parse_json_list(cv.get("domaines"))
    types_cv = _parse_json_list(cv.get("types_contrat_souhaites"))
    annees_cv: Optional[int] = cv.get("annees_experience")
    lieu_cv: Optional[str] = cv.get("localisation_preferee")

    texte_offre = " ".join(
        str(v) for v in [
            offre.get("titre", ""),
            offre.get("description", ""),
            offre.get("resume_ia", ""),
            offre.get("lieu", ""),
            offre.get("type_contrat_clarifie", "") or offre.get("type_contrat", ""),
        ] if v
    )
    lieu_offre: Optional[str] = offre.get("lieu")
    type_offre: Optional[str] = offre.get("type_contrat_clarifie") or offre.get("type_contrat")

    sc = score_competences(competences_cv, texte_offre)

    # Boost postes_cibles (Notes ADH) : +25 si au moins une expression trouvée
    postes_cibles_raw = (cv.get("postes_cibles") or "").strip()
    postes_cibles_trouves: list[str] = []
    if postes_cibles_raw:
        texte_offre_norm = normaliser(texte_offre)
        expressions = [
            e.strip()
            for e in postes_cibles_raw.replace("\n", ",").split(",")
            if e.strip()
        ]
        for expr in expressions:
            if normaliser(expr) in texte_offre_norm:
                postes_cibles_trouves.append(expr)
        if postes_cibles_trouves:
            sc = min(100, sc + 25)

    sd = score_domaine(domaines_cv, texte_offre)
    se = score_experience(annees_cv, texte_offre)
    sct = score_contrat(types_cv, type_offre)
    sl = score_lieu(lieu_cv, lieu_offre)

    global_ = round(
        sc  * POIDS["competences"] +
        sd  * POIDS["domaine"] +
        se  * POIDS["experience"] +
        sct * POIDS["contrat"] +
        sl  * POIDS["lieu"]
    )

    # Plancher strict : 0 compétence matchée (après boost) = aucun match
    if sc == 0:
        global_ = 0

    details = {
        "score_competences": sc,
        "score_domaine": sd,
        "score_experience": se,
        "score_contrat": sct,
        "score_lieu": sl,
        "nb_competences_cv": len(competences_cv),
        "domaines_cv": domaines_cv,
        "annees_cv": annees_cv,
        "types_contrat_cv": types_cv,
        "lieu_cv": lieu_cv,
        "postes_cibles_trouves": postes_cibles_trouves,
        "plancher_active": sc == 0,
    }

    return {
        "score_global":      global_,
        "score_competences": sc,
        "score_domaine":     sd,
        "score_experience":  se,
        "score_contrat":     sct,
        "score_lieu":        sl,
        "details_json":      json.dumps(details, ensure_ascii=False),
    }
