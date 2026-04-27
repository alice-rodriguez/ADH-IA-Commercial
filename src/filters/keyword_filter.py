"""
Passe 1 — Filtre par mots-clés (100% gratuit, zéro IA).

Objectif : éliminer 70 à 80% des offres non pertinentes AVANT de faire appel
à l'IA, pour réduire le coût au minimum.

Logique :
  - Au moins 1 mot-clé "requis" doit apparaître dans le titre + description
  - Au moins 1 mot-clé "sectoriel" doit apparaître
  - Aucun mot-clé "exclu" ne doit apparaître
  - Score = nombre de mots-clés trouvés (utilisé pour trier avant l'IA)
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def _normaliser_texte(texte: str) -> str:
    """Minuscules, sans accents parasites pour comparaison robuste."""
    return texte.lower()


def _contient(texte: str, mot: str) -> bool:
    """Vérifie si un mot ou expression apparaît dans le texte (mot entier ou expression)."""
    pattern = r"\b" + re.escape(mot.lower()) + r"\b"
    return bool(re.search(pattern, texte))


def evaluer(offre: dict, criteres: dict) -> Tuple[bool, int]:
    """
    Évalue une offre avec les règles mots-clés.

    Retourne :
      (True, score)  → offre pertinente, passe à l'IA
      (False, 0)     → offre rejetée définitivement
    """
    texte = _normaliser_texte(
        f"{offre.get('titre', '')} {offre.get('description', '')} {offre.get('entreprise', '')}"
    )

    mots_cles = criteres.get("mots_cles", {})
    requis    = [m.lower() for m in mots_cles.get("requis", [])]
    sectoriels = [m.lower() for m in mots_cles.get("sectoriels", [])]
    boost     = [m.lower() for m in mots_cles.get("boost", [])]
    exclus    = [m.lower() for m in mots_cles.get("exclus", [])]

    # Règle 1 — Mots exclus : rejet immédiat
    for mot in exclus:
        if _contient(texte, mot):
            logger.debug("Offre rejetée (mot exclu '%s') : %s", mot, offre.get("titre"))
            return False, 0

    # Règle 2 — Au moins 1 mot requis
    a_requis = any(_contient(texte, m) for m in requis)
    if not a_requis:
        logger.debug("Offre rejetée (aucun mot requis) : %s", offre.get("titre"))
        return False, 0

    # Règle 3 — Au moins 1 mot sectoriel
    a_sectoriel = any(_contient(texte, m) for m in sectoriels)
    if not a_sectoriel:
        logger.debug("Offre rejetée (aucun secteur) : %s", offre.get("titre"))
        return False, 0

    # Calcul du score
    score = 0
    score += sum(1 for m in requis if _contient(texte, m))
    score += sum(1 for m in sectoriels if _contient(texte, m))
    score += sum(2 for m in boost if _contient(texte, m))  # Les mots boost valent double

    seuil = criteres.get("seuils", {}).get("score_pre_filtre_minimum", 2)
    if score < seuil:
        logger.debug("Offre rejetée (score %d < seuil %d) : %s", score, seuil, offre.get("titre"))
        return False, 0

    return True, score


def filtrer(offres: list, criteres: dict) -> list:
    """
    Applique le filtre mots-clés à toute une liste d'offres.
    Retourne uniquement les offres qui passent, avec leur score.
    """
    retenues = []
    rejets = 0

    for offre in offres:
        ok, score = evaluer(offre, criteres)
        if ok:
            offre["score_pre_filtre"] = score
            retenues.append(offre)
        else:
            rejets += 1

    taux_rejet = (rejets / len(offres) * 100) if offres else 0
    logger.info(
        "Passe 1 (mots-clés) : %d entrées → %d retenues, %d rejetées (%.0f%%)",
        len(offres), len(retenues), rejets, taux_rejet,
    )

    # Tri par score décroissant pour que les meilleures offres passent l'IA en premier
    retenues.sort(key=lambda o: o.get("score_pre_filtre", 0), reverse=True)
    return retenues
