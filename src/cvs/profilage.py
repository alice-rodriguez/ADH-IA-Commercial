"""Profilage d'un CV via Claude Haiku 4.5.

Extrait des données structurées du texte brut d'un CV.
"""
import json
import logging
import os
from typing import Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

MODELE = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024

PROMPT_SYSTEME = """Tu es un assistant qui analyse des CVs et extrait des informations structurées.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans préambule, sans commentaire.
Le JSON doit suivre EXACTEMENT le schéma demandé."""

PROMPT_UTILISATEUR = """Analyse ce CV et extrais les informations suivantes en JSON :

{{
  "nom_candidat": "Prénom NOM",
  "titre_courant": "Titre du poste actuel ou recherché",
  "competences_techniques": ["compétence1", "compétence2", ...],
  "domaines": ["domaine1", "domaine2", ...],
  "annees_experience": <nombre entier ou null>,
  "types_contrat_souhaites": ["CDI", "Freelance", "CDD", ...],
  "localisation_preferee": "<lieu ou null>",
  "tjm_moyen": <nombre entier en EUR ou null>,
  "salaire_souhaite": <nombre entier en EUR ou null>
}}

Règles :
- competences_techniques : 5 à 20 entrées, technos/outils/méthodes (ex: SAP, JIRA, Scrum, ITIL, ALM, Java, AWS...)
- domaines : 3 à 10 entrées — secteurs métier ET domaines fonctionnels, en français OU en anglais tel qu'écrit dans le CV (ex: banque, assurance, énergie, santé, telecom, Trade Finance, Cash Management, Corporate Banking, Capital Markets, Retail Banking, Supply Chain, Insurance, Public Sector, Leasing, Automotive) — inclure OBLIGATOIREMENT tout domaine sectoriel ou fonctionnel mentionné au moins 2 fois dans le CV
- annees_experience : déduis du parcours ou null si impossible à estimer
- types_contrat_souhaites : []  si non explicite ; sinon CDI/Freelance/CDD/Stage/Alternance
- localisation_preferee : ville ou région ; "remote" si full remote ; null si non précisé
- tjm_moyen : seulement si mentionné explicitement, sinon null
- salaire_souhaite : pareil

CV à analyser :

---
{texte_cv}
---

Réponds UNIQUEMENT avec le JSON, rien d'autre."""


def profiler_cv(texte_brut: str) -> Optional[dict]:
    """Profile un CV via Claude Haiku.

    Returns:
        Dict avec les champs structurés ou None si échec.
    """
    if not texte_brut or len(texte_brut) < 100:
        logger.warning("Texte trop court (< 100 car.), profilage skip.")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY non définie.")
        return None

    client = Anthropic(api_key=api_key)
    contenu = ""

    try:
        prompt = PROMPT_UTILISATEUR.replace("{texte_cv}", texte_brut[:8000])

        response = client.messages.create(
            model=MODELE,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user", "content": prompt}],
        )

        contenu = response.content[0].text.strip()
        if contenu.startswith("```"):
            contenu = contenu.split("```")[1]
            if contenu.startswith("json"):
                contenu = contenu[4:]
            contenu = contenu.strip()

        data = json.loads(contenu)

        clefs_attendues = {
            "nom_candidat", "titre_courant", "competences_techniques",
            "domaines", "annees_experience", "types_contrat_souhaites",
            "localisation_preferee", "tjm_moyen", "salaire_souhaite",
        }
        if not clefs_attendues.issubset(data.keys()):
            manquantes = clefs_attendues - set(data.keys())
            logger.warning("Clés manquantes dans le profil : %s", manquantes)
            for k in manquantes:
                data[k] = None

        return data

    except json.JSONDecodeError as e:
        logger.error("JSON invalide retourné par Haiku : %s", e)
        logger.error("Contenu reçu : %s", contenu[:500] if contenu else "")
        return None
    except Exception as e:
        logger.error("Erreur profilage : %s", e)
        return None
