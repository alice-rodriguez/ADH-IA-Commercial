"""
Passe 2 — Filtrage IA avec Claude Haiku (modèle le moins cher d'Anthropic).

N'est appelée QUE sur les offres qui ont déjà passé le filtre mots-clés.
Coût estimé : ~€0.001 par offre analysée (Claude Haiku).

Claude Haiku tarif (2025) :
  - Entrée  : $0.25  / 1 million de tokens
  - Sortie  : $1.25  / 1 million de tokens
"""

import logging
import json
import os

import anthropic

logger = logging.getLogger(__name__)

MODELE = "claude-haiku-4-5-20251001"
TARIF_ENTREE  = 0.25 / 1_000_000   # $ par token
TARIF_SORTIE  = 1.25 / 1_000_000   # $ par token
EUR_USD       = 0.92                 # taux de conversion approximatif


def analyser_offre(offre: dict, criteres: dict, client: anthropic.Anthropic) -> dict:
    """
    Envoie une offre à Claude Haiku pour :
    - Attribution d'un score de pertinence (0-100)
    - Génération d'un résumé en français (3 lignes max)
    - Classification du type de contrat

    Retourne l'offre enrichie avec score_ia et resume_ia.
    """
    profils = ", ".join(criteres.get("profils", []))
    secteurs = ", ".join(criteres.get("secteurs", []))

    prompt = f"""Tu es un expert en recrutement pour un cabinet de conseil.
Tu dois évaluer si cette offre correspond à nos critères de placement.

CRITÈRES DE NOTRE CABINET :
- Profils placés : {profils}
- Secteurs : {secteurs}
- Localisation : Île-de-France, Remote ou Hybride
- Niveau requis : profils confirmés (minimum 3-5 ans d'expérience)

OFFRE À ANALYSER :
Titre : {offre.get('titre', '')}
Entreprise : {offre.get('entreprise', '')}
Lieu : {offre.get('lieu', '')}
Type de contrat : {offre.get('type_contrat', '')}
Description : {offre.get('description', '')[:800]}

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans explication) :
{{
  "score": <entier entre 0 et 100>,
  "resume": "<résumé en 2-3 lignes en français>",
  "type_contrat_clarifie": "<CDI|CDD|Freelance|Mission|Appel d'offres>"
}}

Score 0-100 :
  90-100 = Parfaitement dans notre cœur de cible
  70-89  = Très pertinent
  50-69  = Pertinent mais quelques doutes
  30-49  = Peu pertinent
  0-29   = Hors cible"""

    try:
        reponse = client.messages.create(
            model=MODELE,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        # Calcul du coût
        tokens_entree = reponse.usage.input_tokens
        tokens_sortie = reponse.usage.output_tokens
        cout_usd = tokens_entree * TARIF_ENTREE + tokens_sortie * TARIF_SORTIE
        cout_eur = cout_usd * EUR_USD
        logger.debug(
            "IA [%s] : score=%s — tokens %d/%d — coût €%.5f",
            offre.get("titre", "")[:40], "?", tokens_entree, tokens_sortie, cout_eur,
        )

        contenu = reponse.content[0].text.strip()
        # Nettoyage si Claude ajoute des backticks malgré la consigne
        contenu = contenu.replace("```json", "").replace("```", "").strip()
        resultat = json.loads(contenu)

        offre["score_ia"] = int(resultat.get("score", 0))
        offre["resume_ia"] = resultat.get("resume", "")
        offre["type_contrat"] = resultat.get("type_contrat_clarifie", offre.get("type_contrat", ""))
        offre["cout_ia_eur"] = cout_eur

        return offre

    except json.JSONDecodeError as e:
        logger.warning("Réponse IA non-JSON pour '%s' : %s", offre.get("titre"), e)
        offre["score_ia"] = 0
        offre["resume_ia"] = "Analyse impossible"
        offre["cout_ia_eur"] = 0.0
        return offre
    except Exception as e:
        logger.error("Erreur IA pour '%s' : %s", offre.get("titre"), e)
        offre["score_ia"] = 0
        offre["resume_ia"] = "Analyse impossible"
        offre["cout_ia_eur"] = 0.0
        return offre


def filtrer(offres: list, criteres: dict) -> tuple[list, float]:
    """
    Applique le filtre IA sur toutes les offres passées en paramètre.

    Retourne :
      - La liste des offres retenues (score >= seuil)
      - Le coût total en euros
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY manquante — filtre IA désactivé")
        return offres, 0.0

    client = anthropic.Anthropic(api_key=api_key)
    seuil = criteres.get("seuils", {}).get("score_ia_minimum", 60)

    retenues = []
    cout_total = 0.0

    for offre in offres:
        offre_analysee = analyser_offre(offre, criteres, client)
        cout_total += offre_analysee.get("cout_ia_eur", 0.0)

        if offre_analysee.get("score_ia", 0) >= seuil:
            retenues.append(offre_analysee)
            logger.info(
                "[AI-ACCEPT] %s | %s | score=%d",
                offre_analysee.get("source", "?"),
                offre_analysee.get("titre", "")[:60],
                offre_analysee.get("score_ia", 0),
            )
        else:
            logger.info(
                "[AI-REJECT] %s | %s | score=%d | %s",
                offre_analysee.get("source", "?"),
                offre_analysee.get("titre", "")[:60],
                offre_analysee.get("score_ia", 0),
                offre_analysee.get("resume_ia", "")[:120],
            )

    logger.info(
        "Passe 2 (IA) : %d analysées → %d retenues — coût total : €%.4f",
        len(offres), len(retenues), cout_total,
    )

    return retenues, cout_total
