"""Analyse IA d'un couple (CV, offre) via Claude Haiku (CV.2.bis.3.ter)."""

import json
import logging
import os

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

PROMPT_TEMPLATE = """\
Tu es un consultant RH expert en recrutement IT. Analyse la compatibilité entre ce candidat et cette offre.

## Candidat
Nom : {nom}
Titre actuel : {titre}
Expérience : {annees} ans
Localisation : {lieu}
Compétences techniques : {competences}
Domaines : {domaines}
Type de contrat souhaité : {contrat}
Postes cibles (Notes ADH) : {postes_cibles}
TJM : {tjm}€
Disponibilité : {disponibilite}

## Offre
Titre : {titre_offre}
Type de contrat : {type_contrat}
Lieu : {lieu_offre}
Description :
{description}

## Scores algorithmiques (à titre indicatif)
Score global : {score_global}%
Compétences : {score_competences}%
Domaine : {score_domaine}%
Expérience : {score_experience}%

## Consigne
Analyse la compatibilité réelle entre ce candidat et cette offre.
Retourne UNIQUEMENT un objet JSON valide avec exactement ces clés :
- score_ia (entier 0-100) : ton évaluation globale de la compatibilité
- verdict (chaîne) : exactement l'une de ces quatre valeurs : "Excellent candidat", "Bon candidat", "Candidat partiel", "Hors profil"
- explication (chaîne) : 2-3 phrases expliquant la compatibilité globale
- points_forts (tableau de chaînes) : 2-4 points forts du candidat pour ce poste
- points_faibles (tableau de chaînes) : 1-3 points d'attention ou manques
- questions_a_poser (tableau de chaînes) : 2-3 questions clés à poser lors d'un entretien

Réponds UNIQUEMENT avec le JSON, sans aucun texte avant ou après.\
"""


def _parse_list(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) or []
    except (json.JSONDecodeError, TypeError):
        return []


def analyser_couple(cv: dict, offre: dict, scores: dict | None = None) -> dict | None:
    """Appelle Haiku pour analyser la compatibilité CV ↔ offre.

    Returns:
        dict with keys: score_ia, verdict, explication, points_forts,
        points_faibles, questions_a_poser
        None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY non définie — analyse IA impossible")
        return None

    competences = _parse_list(cv.get("competences_techniques"))
    domaines = _parse_list(cv.get("domaines"))
    types_contrat = _parse_list(cv.get("types_contrat_souhaites"))

    tjm = cv.get("tjm_negocie") or cv.get("tjm_moyen") or "Non renseigné"

    prompt = PROMPT_TEMPLATE.format(
        nom=cv.get("nom_candidat") or "Non renseigné",
        titre=cv.get("titre_courant") or "Non renseigné",
        annees=cv.get("annees_experience") or "Non renseigné",
        lieu=cv.get("localisation_preferee") or "Non renseigné",
        competences=", ".join(competences) if competences else "Non renseignées",
        domaines=", ".join(domaines) if domaines else "Non renseignés",
        contrat=", ".join(types_contrat) if types_contrat else "Non renseigné",
        postes_cibles=cv.get("postes_cibles") or "Non renseignés",
        tjm=tjm,
        disponibilite=cv.get("disponibilite") or "Non renseignée",
        titre_offre=offre.get("titre") or "",
        type_contrat=offre.get("type_contrat_clarifie") or offre.get("type_contrat") or "",
        lieu_offre=offre.get("lieu") or "",
        description=(offre.get("description") or "")[:2000],
        score_global=scores.get("score_global", "?") if scores else "?",
        score_competences=scores.get("score_competences", "?") if scores else "?",
        score_domaine=scores.get("score_domaine", "?") if scores else "?",
        score_experience=scores.get("score_experience", "?") if scores else "?",
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.startswith("json"):
                text = text[4:].lstrip("\n")
            if text.endswith("```"):
                text = text[:-3].rstrip()
        result = json.loads(text)
        required = {
            "score_ia", "verdict", "explication",
            "points_forts", "points_faibles", "questions_a_poser",
        }
        if not required.issubset(result.keys()):
            logger.error("Réponse Haiku incomplète — clés manquantes : %s",
                         required - result.keys())
            return None
        return result
    except Exception as e:
        logger.error("Erreur appel Haiku : %s", e)
        return None
