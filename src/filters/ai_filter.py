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

# Au-delà de ce nombre d'échecs CONSÉCUTIFS avec la même erreur (crédit épuisé,
# clé invalide…), l'IA est jugée injoignable : le filtre s'interrompt au lieu
# de rejeter silencieusement toutes les offres restantes.
SEUIL_ECHECS_CONSECUTIFS = 10


def classer_erreur(e: Exception) -> tuple[str, str]:
    """(signature, libellé lisible) d'une erreur d'appel à l'API Anthropic.

    La signature sert à reconnaître « la même erreur » d'un appel à l'autre ;
    elle ne contient pas le message brut (identifiant de requête variable).
    """
    message = str(e)
    statut = getattr(e, "status_code", None)
    if "credit balance" in message.lower():
        return "credit", "crédit API Anthropic épuisé"
    if isinstance(e, anthropic.AuthenticationError) or statut == 401:
        return "cle", "clé API Anthropic invalide ou révoquée"
    if isinstance(e, anthropic.PermissionDeniedError) or statut == 403:
        return "permission", "accès refusé par l'API Anthropic (403)"
    detail = f"{type(e).__name__}" + (f" ({statut})" if statut else "")
    return f"autre:{type(e).__name__}:{statut}", f"autre erreur : {detail} — {message[:150]}"


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
    types_contrat = ", ".join(criteres.get("types_contrat", []))

    # Marché public (BOAMP) : ce n'est pas une mission freelance, sans cette
    # précision l'IA risque de rejeter la source en bloc.
    clause_source = ""
    if offre.get("source") == "BOAMP":
        clause_source = """
CAS PARTICULIER — MARCHÉ PUBLIC (BOAMP) :
- Cette offre est un marché public auquel ADH répond directement, sans ESN
  intermédiaire. Ce mode de contractualisation est recherché : il ne doit
  jamais faire baisser le score.
- Le critère de pertinence reste le métier : pilotage de projet, AMOA,
  conduite du changement sur système d'information.
"""

    prompt = f"""Tu es un expert en recrutement pour un cabinet de conseil.
Tu dois évaluer si cette offre correspond à nos critères de placement.

CRITÈRES DE NOTRE CABINET :
- Profils placés : {profils}
- Secteurs : {secteurs}
- Types de contrat acceptés, tous sur un pied d'égalité : {types_contrat}
  La mission freelance est un mode de placement normal pour notre cabinet :
  le type de contrat ne doit jamais faire baisser le score.
- Localisation : Île-de-France, Remote ou Hybride
  Si le lieu est absent ou imprécis, c'est une information manquante neutre :
  ne pénalise pas l'offre et ne la rejette pas pour ce motif.
- Niveau requis : profils confirmés (minimum 3-5 ans d'expérience)
{clause_source}
OFFRE À ANALYSER :
Titre : {offre.get('titre', '')}
Entreprise : {offre.get('entreprise', '')}
Lieu : {offre.get('lieu') or 'non précisé'}
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
        # L'appel n'a pas abouti : l'offre n'a PAS été analysée (≠ score 0 réel)
        offre["erreur_ia"] = classer_erreur(e)
        return offre


def filtrer(offres: list, criteres: dict, rapport: dict | None = None,
            a_chaque_offre=None) -> tuple[list, float]:
    """
    Applique le filtre IA sur toutes les offres passées en paramètre.

    Retourne :
      - La liste des offres retenues (score >= seuil)
      - Le coût total en euros

    rapport (optionnel) : dict rempli avec "analysees", "echecs", "interrompu"
      et "cause" (libellé lisible si le filtre s'est interrompu).
    a_chaque_offre (optionnel) : appelée avec chaque offre juste après son
      analyse (permet d'écrire le résultat au fil de l'eau).

    Interruption : après SEUIL_ECHECS_CONSECUTIFS échecs consécutifs avec la
    même erreur, les offres restantes ne sont pas envoyées à l'IA.
    """
    if rapport is None:
        rapport = {}
    rapport.update({"analysees": 0, "echecs": 0, "interrompu": False, "cause": None})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY manquante — filtre IA désactivé")
        return offres, 0.0

    client = anthropic.Anthropic(api_key=api_key)
    seuil = criteres.get("seuils", {}).get("score_ia_minimum", 60)

    retenues = []
    cout_total = 0.0
    signature_precedente, nb_consecutifs = None, 0

    for offre in offres:
        offre_analysee = analyser_offre(offre, criteres, client)
        cout_total += offre_analysee.get("cout_ia_eur", 0.0)
        if a_chaque_offre is not None:
            a_chaque_offre(offre_analysee)

        erreur = offre_analysee.get("erreur_ia")
        if erreur:
            rapport["echecs"] += 1
            signature, libelle = erreur
            nb_consecutifs = nb_consecutifs + 1 if signature == signature_precedente else 1
            signature_precedente = signature
            if nb_consecutifs >= SEUIL_ECHECS_CONSECUTIFS:
                rapport["interrompu"] = True
                rapport["cause"] = libelle
                logger.error(
                    "FILTRE IA INTERROMPU : %d échecs consécutifs — %s. "
                    "%d offre(s) non envoyée(s) à l'IA (reprises par scripts/rattrapage_ia.py).",
                    nb_consecutifs, libelle, len(offres) - rapport["analysees"] - rapport["echecs"],
                )
                break
            continue
        signature_precedente, nb_consecutifs = None, 0
        rapport["analysees"] += 1

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
        "Passe 2 (IA) : %d soumises, %d analysées, %d en échec → %d retenues — coût total : €%.4f%s",
        len(offres), rapport["analysees"], rapport["echecs"], len(retenues), cout_total,
        f" — INTERROMPU ({rapport['cause']})" if rapport["interrompu"] else "",
    )

    return retenues, cout_total
