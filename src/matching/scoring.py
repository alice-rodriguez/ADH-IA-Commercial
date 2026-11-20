"""Fonctions de scoring pour le matching CVs ↔ offres (MATCH-01).

Score global = moyenne pondérée des critères ÉVALUÉS pour ce couple. Un critère
NEUTRE (information absente ou non pertinente) ne consomme pas de poids : son
poids est redistribué sur les critères qui ont réellement une valeur.

Critères (0–100) :
  postes      postes ciblés de la fiche ADH (saisis par Alice) comparés au titre de l'offre
  competences proportion des compétences du CV présentes dans l'offre
  lieu        zones géographiques (département / région), mobilité de la fiche prioritaire
  experience  seulement si l'offre exige une ancienneté ET que celle du CV est connue
  contrat     seulement si l'offre précise un contrat ET que le candidat a des préférences
  domaine     BONUS : évalué (100) seulement s'il y a recouvrement sectoriel ; sinon neutre

Garanties de classement :
  - un candidat dont un poste ciblé figure dans le titre de l'offre voit son score
    ramené dans [PLANCHER_POSTE_DANS_TITRE, 100] (remise à l'échelle, l'ordre entre
    eux est conservé) ; un candidat dont les postes ciblés sont RENSEIGNÉS mais dont
    aucun ne correspond plafonne juste en dessous : il ne peut jamais passer devant ;
  - un candidat dont le champ postes ciblés est VIDE n'est ni promu ni plafonné : le
    critère est NEUTRE (l'outil ne sait rien), son poids est redistribué ;
  - aucun signal métier (ni poste ciblé trouvé, ni compétence trouvée) → score 0.
"""

import json
import logging
import re
from typing import Optional

from src.filters.keyword_filter import _motif, _normaliser_texte, _normaliser_titre
from src.matching.geo import REGION_DE, mentionne_teletravail, zones
from src.matching.utils import (
    SYNONYMES_COMPETENCES,
    VARIANTES_DOMAINES,
    _domaines_cv_normalises,
    extraire_annees_requises,
    normaliser,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# RÉGLAGES — tous les poids et paliers du matching, à ajuster ici uniquement
# ═══════════════════════════════════════════════════════════════════════════

POIDS = {
    # Postes ciblés saisis par Alice : le signal le plus fiable, au moins autant
    # que les compétences (exigence MATCH-01).
    "postes":      35,
    # Compétences extraites du CV par le profilage.
    "competences": 30,
    # Zone géographique (mobilité de la fiche ADH, sinon localisation du CV).
    "lieu":        10,
    # Ancienneté : seulement si l'offre l'exige (sinon neutre).
    "experience":  10,
    # Secteur : bonus seulement (évalué à 100 en cas de recouvrement, neutre sinon).
    "domaine":     10,
    # Type de contrat : seulement si l'offre le précise ET le candidat a des préférences.
    "contrat":      5,
}

# Score « postes ciblés » : qualité de la meilleure correspondance + bonus par
# correspondance supplémentaire.
POSTE_DANS_TITRE = 80          # un poste ciblé figure dans le titre de l'offre
POSTE_DANS_DESCRIPTION = 40    # trouvé seulement dans la description
BONUS_POSTE_SUPPLEMENTAIRE = 10

# Garantie de classement (voir docstring du module)
PLANCHER_POSTE_DANS_TITRE = 60
PLAFOND_SANS_POSTE = PLANCHER_POSTE_DANS_TITRE - 1   # postes ciblés renseignés, aucun ne correspond

# Score de lieu
LIEU_MEME_DEPARTEMENT = 100    # ou zone du candidat couvrant la zone de l'offre (« IDF », « France entière »)
LIEU_MEME_REGION = 80          # ex. Cergy (95) / Vélizy (78)
LIEU_AUTRE_REGION = 0

# Valeur enregistrée dans les colonnes score_* pour un critère neutre (la colonne
# est NOT NULL) ; le global ne l'utilise pas, details_json["neutres"] le signale.
VALEUR_NEUTRE_STOCKEE = 50

# Séparateurs des postes ciblés saisis à la main (« Business Analyst, MOA ; AMOA / PMO »)
_SEPARATEURS_POSTES = re.compile(r"[,;\n/|]+|\s+-\s+")


# ---------------------------------------------------------------------------
# Critères (renvoient un entier 0–100, ou None si NEUTRE)
# ---------------------------------------------------------------------------


def score_competences(competences_cv: list[str], texte_offre: str) -> int:
    """Proportion de compétences du CV trouvées dans le texte de l'offre (synonymes compris)."""
    if not competences_cv or not texte_offre:
        return 0
    texte_norm = normaliser(texte_offre)
    trouvees = 0
    for c in competences_cv:
        c_norm = normaliser(c)
        if c_norm in texte_norm:
            trouvees += 1
            continue
        synonymes = SYNONYMES_COMPETENCES.get(c) or SYNONYMES_COMPETENCES.get(c.title()) or []
        if any(s in texte_norm for s in synonymes):
            trouvees += 1
    return round(100 * trouvees / len(competences_cv))


def postes_cibles(cv: dict) -> list[str]:
    brut = (cv.get("postes_cibles") or "").strip()
    return [p.strip() for p in _SEPARATEURS_POSTES.split(brut) if p.strip()]


def score_postes(postes: list[str], titre_offre: str, description_offre: str) -> tuple[Optional[int], list[dict]]:
    """(score ou None si le candidat n'a pas de poste ciblé, correspondances).

    Comparaison tolérante de keyword_filter (pluriels, féminins, accents, apostrophes,
    « Chef(fe) de projet »). Meilleure correspondance + bonus par poste supplémentaire.
    """
    if not postes:
        return None, []
    titre = _normaliser_titre(titre_offre or "")
    description = _normaliser_texte(description_offre or "")
    trouves = []
    for p in postes:
        motif = _motif(p)
        if motif.search(titre):
            trouves.append({"poste": p, "ou": "titre"})
        elif motif.search(description):
            trouves.append({"poste": p, "ou": "description"})
    if not trouves:
        return 0, []
    meilleur = POSTE_DANS_TITRE if any(t["ou"] == "titre" for t in trouves) else POSTE_DANS_DESCRIPTION
    return min(100, meilleur + BONUS_POSTE_SUPPLEMENTAIRE * (len(trouves) - 1)), trouves


def score_domaine(domaines_cv: list[str], texte_offre: str) -> tuple[Optional[int], list[str]]:
    """Bonus sectoriel : 100 si au moins un secteur du CV figure dans l'offre, sinon NEUTRE."""
    if not domaines_cv or not texte_offre:
        return None, []
    texte_norm = normaliser(texte_offre)
    communs = [cle for cle in sorted(_domaines_cv_normalises(domaines_cv))
               if any(v in texte_norm for v in VARIANTES_DOMAINES[cle])]
    return (100, communs) if communs else (None, [])


def score_experience(annees_cv: Optional[int], texte_offre: str) -> tuple[Optional[int], Optional[int]]:
    """(score ou None, années exigées). Évalué seulement si l'offre exige une ancienneté
    et que celle du CV est connue ; au-dessous de l'exigence, proportionnel."""
    requises = extraire_annees_requises(texte_offre)
    if requises is None or annees_cv is None or requises <= 0:
        return None, requises
    if annees_cv >= requises:
        return 100, requises
    return round(100 * annees_cv / requises), requises


def score_contrat(types_cv: list[str], type_offre: Optional[str]) -> Optional[int]:
    """Évalué seulement si l'offre précise un contrat ET que le candidat a des préférences."""
    if not types_cv or not type_offre:
        return None
    type_offre_norm = normaliser(type_offre)
    for t in types_cv:
        t_norm = normaliser(t)
        if t_norm and (t_norm in type_offre_norm or type_offre_norm in t_norm):
            return 100
        if t_norm in ("freelance", "independant") and any(
            k in type_offre_norm for k in ("freelance", "independant", "mission")
        ):
            return 100
    return 0


def score_lieu(lieu_candidat: str, lieu_offre: str) -> tuple[Optional[int], str]:
    """(score ou None si NEUTRE, explication). Par zones, jamais par égalité de chaînes.

    Neutre : lieu inconnu côté candidat ou côté offre, ou offre en télétravail
    (la contrainte de lieu disparaît). Une inconnue n'est donc jamais mieux notée
    qu'une correspondance régionale réelle.
    """
    if lieu_offre and mentionne_teletravail(lieu_offre):
        return None, "offre en télétravail"
    z_cand, z_offre = zones(lieu_candidat), zones(lieu_offre)
    if not z_cand or not z_offre:
        return None, "lieu inconnu"
    if z_offre <= z_cand or z_cand & z_offre:
        return LIEU_MEME_DEPARTEMENT, "même zone"
    regions_cand = {REGION_DE[d] for d in z_cand if d in REGION_DE}
    regions_offre = {REGION_DE[d] for d in z_offre if d in REGION_DE}
    if regions_cand & regions_offre:
        return LIEU_MEME_REGION, "même région"
    return LIEU_AUTRE_REGION, "autre région"


# ---------------------------------------------------------------------------
# Score global
# ---------------------------------------------------------------------------


def _parse_json_list(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) or []
    except (json.JSONDecodeError, TypeError):
        return []


def calculer_score_global(cv: dict, offre: dict) -> dict:
    """Calcule tous les scores pour un couple (CV, offre).

    Returns:
        Dict avec score_global, score_competences, score_domaine, score_experience,
        score_contrat, score_lieu (colonnes de la table matchings), score_postes
        et details_json.
    """
    competences_cv = _parse_json_list(cv.get("competences_techniques"))
    domaines_cv = _parse_json_list(cv.get("domaines"))
    types_cv = _parse_json_list(cv.get("types_contrat_souhaites"))
    annees_cv: Optional[int] = cv.get("annees_experience")
    # Mobilité saisie par Alice sur la fiche, prioritaire sur la localisation extraite du CV
    mobilite = (cv.get("mobilite") or "").strip()
    localisation = (cv.get("localisation_preferee") or "").strip()
    lieu_candidat = mobilite if zones(mobilite) else (localisation or mobilite)
    source_lieu = "mobilite" if lieu_candidat and lieu_candidat == mobilite else ("localisation_preferee" if lieu_candidat else None)

    titre = offre.get("titre") or ""
    description = " ".join(str(v) for v in [offre.get("description"), offre.get("resume_ia")] if v)
    texte_offre = " ".join(
        str(v) for v in [
            titre, offre.get("description", ""), offre.get("resume_ia", ""), offre.get("lieu", ""),
            offre.get("type_contrat_clarifie", "") or offre.get("type_contrat", ""),
        ] if v
    )
    lieu_offre = offre.get("lieu") or ""
    type_offre: Optional[str] = offre.get("type_contrat_clarifie") or offre.get("type_contrat")

    sp, postes_trouves = score_postes(postes_cibles(cv), titre, description)
    sc = score_competences(competences_cv, texte_offre)
    sd, domaines_communs = score_domaine(domaines_cv, texte_offre)
    se, annees_requises = score_experience(annees_cv, texte_offre)
    sct = score_contrat(types_cv, type_offre)
    sl, lieu_explication = score_lieu(lieu_candidat, lieu_offre)

    valeurs = {"postes": sp, "competences": sc, "lieu": sl, "experience": se, "domaine": sd, "contrat": sct}
    evalues = {k: v for k, v in valeurs.items() if v is not None}
    poids_total = sum(POIDS[k] for k in evalues)
    brut = sum(POIDS[k] * v for k, v in evalues.items()) / poids_total if poids_total else 0

    poste_dans_titre = any(t["ou"] == "titre" for t in postes_trouves)
    aucun_signal_metier = not postes_trouves and sc == 0
    if aucun_signal_metier:
        global_, palier = 0, "aucun signal métier (ni poste ciblé ni compétence trouvés)"
    elif poste_dans_titre:
        # [0, 100] → [PLANCHER, 100] : garantie de rang sans écraser les écarts entre candidats
        global_ = round(PLANCHER_POSTE_DANS_TITRE + (100 - PLANCHER_POSTE_DANS_TITRE) * brut / 100)
        palier = "poste ciblé dans le titre (échelle 60-100)"
    elif sp is None:
        # Champ postes ciblés vide : critère neutre (poids redistribué), aucun plafond
        global_, palier = round(brut), "postes ciblés non renseignés (critère neutre)"
    elif not postes_trouves:
        global_, palier = min(round(brut), PLAFOND_SANS_POSTE), "aucun poste ciblé correspondant (plafond)"
    else:
        global_, palier = round(brut), "poste ciblé dans la description"

    details = {
        "version": "MATCH-01",
        "score_postes": sp,
        "postes_cibles_trouves": [t["poste"] for t in postes_trouves],
        "postes_correspondances": postes_trouves,
        "score_competences": sc,
        "score_domaine": sd,
        "score_experience": se,
        "score_contrat": sct,
        "score_lieu": sl,
        "neutres": sorted(k for k, v in valeurs.items() if v is None),
        "poids_effectifs": {k: round(POIDS[k] / poids_total, 3) for k in evalues} if poids_total else {},
        "score_brut": round(brut, 1),
        "palier": palier,
        "nb_competences_cv": len(competences_cv),
        "domaines_cv": domaines_cv,
        "domaines_communs": domaines_communs,
        "annees_cv": annees_cv,
        "annees_requises": annees_requises,
        "types_contrat_cv": types_cv,
        "lieu_cv": lieu_candidat or None,
        "lieu_cv_source": source_lieu,
        "lieu_explication": lieu_explication,
        "plancher_active": aucun_signal_metier,
    }

    def colonne(v):
        return VALEUR_NEUTRE_STOCKEE if v is None else v

    return {
        "score_global":      global_,
        "score_competences": sc,
        "score_domaine":     colonne(sd),
        "score_experience":  colonne(se),
        "score_contrat":     colonne(sct),
        "score_lieu":        colonne(sl),
        "score_postes":      sp,
        "details_json":      json.dumps(details, ensure_ascii=False),
    }
