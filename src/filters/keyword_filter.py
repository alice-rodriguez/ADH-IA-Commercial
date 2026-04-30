"""
Passe 1 — Filtre par mots-clés (100% gratuit, zéro IA).

Objectif : éliminer 70 à 80% des offres non pertinentes AVANT de faire appel
à l'IA, pour réduire le coût au minimum.

Logique :
  - Au moins 1 mot-clé "requis" doit apparaître dans le titre + description
  - Au moins 1 mot-clé "sectoriel" doit apparaître
  - Aucun mot-clé "exclu" ne doit apparaître dans le TITRE (pas la description)
  - Score = nombre de mots-clés trouvés (utilisé pour trier avant l'IA)
"""

import re
import logging
from collections import Counter
from typing import Tuple

logger = logging.getLogger(__name__)


def _normaliser_texte(texte: str) -> str:
    """Minuscules, sans accents parasites pour comparaison robuste."""
    return texte.lower()


def _normaliser_titre(titre: str) -> str:
    """
    Retire les parenthèses et leur contenu, normalise les espaces.
    "Chef(fe) de projet" → "chef de projet"
    "Directeur(trice)" → "directeur"
    """
    titre = re.sub(r'\([^)]*\)', '', titre)
    titre = re.sub(r'\s+', ' ', titre).strip()
    return titre.lower()


def _contient(texte: str, mot: str) -> bool:
    """Vérifie si un mot ou expression apparaît dans le texte (mot entier ou expression)."""
    pattern = r"\b" + re.escape(mot.lower()) + r"\b"
    return bool(re.search(pattern, texte))


def evaluer(offre: dict, criteres: dict) -> Tuple[bool, int, str]:
    """
    Évalue une offre avec les règles mots-clés.

    Retourne :
      (True, score, "")        → offre pertinente, passe à l'IA
      (False, 0, raison)       → offre rejetée définitivement
    """
    # Titre normalisé (parenthèses retirées) — utilisé pour les exclusions
    titre_norm = _normaliser_titre(offre.get('titre', ''))

    # Texte complet (titre normalisé + description + entreprise) — pour requis et sectoriels
    texte_complet = _normaliser_texte(
        f"{titre_norm} {offre.get('description', '')} {offre.get('entreprise', '')}"
    )

    mots_cles = criteres.get("mots_cles", {})
    requis    = [m.lower() for m in mots_cles.get("requis", [])]
    sectoriels = [m.lower() for m in mots_cles.get("sectoriels", [])]
    boost     = [m.lower() for m in mots_cles.get("boost", [])]
    exclus    = [m.lower() for m in mots_cles.get("exclus", [])]

    # Règle 1 — Mots exclus : TITRE UNIQUEMENT (la description mentionne souvent
    # "alternance" ou "stage" dans un contexte non-bloquant)
    for mot in exclus:
        if _contient(titre_norm, mot):
            logger.debug("Offre rejetée (mot exclu '%s') : %s", mot, offre.get("titre"))
            return False, 0, f"mot-clé exclusion : {mot}"

    # Règle 2 — Au moins 1 mot requis (titre normalisé + description)
    a_requis = any(_contient(texte_complet, m) for m in requis)
    if not a_requis:
        logger.debug("Offre rejetée (aucun mot requis) : %s", offre.get("titre"))
        return False, 0, "aucun mot-clé profil détecté"

    # Règle 3 — Au moins 1 mot sectoriel (titre + description)
    a_sectoriel = any(_contient(texte_complet, m) for m in sectoriels)
    if not a_sectoriel:
        logger.debug("Offre rejetée (aucun secteur) : %s", offre.get("titre"))
        return False, 0, "aucun secteur détecté"

    # Calcul du score
    score = 0
    score += sum(1 for m in requis if _contient(texte_complet, m))
    score += sum(1 for m in sectoriels if _contient(texte_complet, m))
    score += sum(2 for m in boost if _contient(texte_complet, m))  # Les mots boost valent double

    seuil = criteres.get("seuils", {}).get("score_pre_filtre_minimum", 2)
    if score < seuil:
        logger.debug("Offre rejetée (score %d < seuil %d) : %s", score, seuil, offre.get("titre"))
        return False, 0, f"score {score} < seuil {seuil}"

    return True, score, ""


def filtrer(offres: list, criteres: dict) -> list:
    """
    Applique le filtre mots-clés à toute une liste d'offres.
    Retourne uniquement les offres qui passent, avec leur score.
    """
    retenues = []
    rejets = 0
    # TEMPORAIRE — pour calibrage du pré-filtre
    stats_rejets: Counter = Counter()

    for offre in offres:
        ok, score, raison = evaluer(offre, criteres)
        if ok:
            offre["score_pre_filtre"] = score
            retenues.append(offre)
        else:
            rejets += 1
            # TEMPORAIRE — pour calibrage du pré-filtre
            logger.info(
                "[PREFILTRE-REJECT] %s | %s | raison: %s",
                offre.get("source", "?"),
                offre.get("titre", "")[:80],
                raison,
            )
            if raison.startswith("mot-clé exclusion"):
                stats_rejets["mot-clé exclusion"] += 1
            elif raison == "aucun mot-clé profil détecté":
                stats_rejets["aucun mot-clé profil"] += 1
            elif raison == "aucun secteur détecté":
                stats_rejets["aucun secteur détecté"] += 1
            elif raison.startswith("score"):
                stats_rejets["score < seuil"] += 1
            else:
                stats_rejets["autre"] += 1

    taux_rejet = (rejets / len(offres) * 100) if offres else 0
    logger.info(
        "Passe 1 (mots-clés) : %d entrées → %d retenues, %d rejetées (%.0f%%)",
        len(offres), len(retenues), rejets, taux_rejet,
    )

    # TEMPORAIRE — pour calibrage du pré-filtre
    if stats_rejets:
        lignes = "\n".join(
            f"    {k} : {v}"
            for k, v in sorted(stats_rejets.items(), key=lambda x: -x[1])
        )
        logger.info("[PREFILTRE-STATS] Raisons de rejet :\n%s", lignes)

    # Tri par score décroissant pour que les meilleures offres passent l'IA en premier
    retenues.sort(key=lambda o: o.get("score_pre_filtre", 0), reverse=True)
    return retenues
