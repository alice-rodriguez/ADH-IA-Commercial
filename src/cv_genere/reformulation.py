"""Reformulation du contenu CV par Haiku pour l'adapter à une offre cible."""
import json
import logging
import os

from anthropic import Anthropic

logger = logging.getLogger(__name__)

MODELE = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2048

PROMPT_SYSTEME = """Tu es un expert RH qui rédige des CVs anonymisés pour un cabinet de conseil en recrutement IT.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans préambule, sans commentaire."""

PROMPT_UTILISATEUR = """Tu dois reformuler le profil d'un consultant IT pour le présenter à une offre cible.

PROFIL DU CONSULTANT :
- Titre : {titre_courant}
- Expérience : {annees_experience} ans
- Compétences : {competences}
- Domaines : {domaines}

OFFRE CIBLE :
- Titre : {offre_titre}
- Entreprise : {offre_entreprise}
- Description : {offre_description}

RÈGLES IMPÉRATIVES :
1. ANONYMISATION TOTALE : remplace tous les noms d'entreprises réelles par des descriptions génériques
   (ex: "BNP Paribas" → "Grand établissement bancaire", "Capgemini" → "Grands groupe de conseil IT")
2. Ne mentionne aucun nom propre de personne
3. Mets en avant les compétences pertinentes pour l'offre cible
4. Maximum 3 expériences (les plus pertinentes pour l'offre)
5. Le profil reformulé fait 3 à 5 lignes maximum

Retourne UNIQUEMENT ce JSON (aucun texte avant ou après) :
{{
  "profil_reformule": "Paragraphe de présentation du consultant, 3-5 lignes, qui met en avant sa valeur ajoutée pour cette offre spécifique.",
  "competences_top6": ["compétence1", "compétence2", "compétence3", "compétence4", "compétence5", "compétence6"],
  "experiences": [
    {{
      "poste": "Titre du poste (générique si besoin)",
      "entreprise": "Description générique anonyme de l'entreprise",
      "periode": "AAAA – AAAA",
      "description": "2-3 lignes décrivant les missions et résultats clés, anonymisées."
    }}
  ],
  "formations": ["Diplôme ou formation (si déductible du parcours, sinon liste vide)"],
  "certifications": ["Certification (si déductible, sinon liste vide)"],
  "secteurs": "Secteur1 · Secteur2 · Secteur3",
  "langues": [{{"nom": "Français", "niveau": "Natif"}}]
}}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else ""
        if text.startswith("json"):
            text = text[4:].lstrip("\n")
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return text


def reformuler_avec_haiku(cv_data: dict, offre_data: dict) -> dict:
    """Reformule le contenu du CV pour le cibler sur une offre.

    Returns:
        dict avec profil_reformule, competences_top6, experiences,
        formations, certifications, secteurs, langues.

    Raises:
        RuntimeError si l'API ou le parsing échoue.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY non définie — impossible de reformuler le CV.")

    competences = cv_data.get("competences_techniques") or []
    if isinstance(competences, str):
        try:
            competences = json.loads(competences)
        except json.JSONDecodeError:
            competences = [c.strip() for c in competences.split(",") if c.strip()]

    domaines = cv_data.get("domaines") or []
    if isinstance(domaines, str):
        try:
            domaines = json.loads(domaines)
        except json.JSONDecodeError:
            domaines = [d.strip() for d in domaines.split(",") if d.strip()]

    prompt = PROMPT_UTILISATEUR.format(
        titre_courant=cv_data.get("titre_courant") or "Consultant IT",
        annees_experience=cv_data.get("annees_experience") or "N/A",
        competences=", ".join(competences[:20]) if competences else "Non précisé",
        domaines=", ".join(domaines[:10]) if domaines else "Non précisé",
        offre_titre=offre_data.get("titre") or "",
        offre_entreprise=offre_data.get("entreprise") or "Non précisé",
        offre_description=(offre_data.get("description") or "")[:2000],
    )

    client = Anthropic(api_key=api_key)
    contenu = ""

    try:
        response = client.messages.create(
            model=MODELE,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=PROMPT_SYSTEME,
            messages=[{"role": "user", "content": prompt}],
        )
        contenu = response.content[0].text.strip()
        contenu = _strip_fences(contenu)
        data = json.loads(contenu)
    except json.JSONDecodeError as e:
        logger.error("JSON invalide retourné par Haiku : %s", e)
        logger.error("Contenu : %s", contenu[:500])
        raise RuntimeError(f"Réponse Haiku non parseable : {e}")
    except Exception as e:
        logger.error("Erreur appel Haiku : %s", e)
        raise RuntimeError(f"Erreur lors de l'appel Haiku : {e}")

    # Garantir les clés minimales
    data.setdefault("profil_reformule", "")
    data.setdefault("competences_top6", competences[:6])
    data.setdefault("experiences", [])
    data.setdefault("formations", [])
    data.setdefault("certifications", [])
    data.setdefault("secteurs", " · ".join(domaines[:5]) if domaines else "")
    data.setdefault("langues", [{"nom": "Français", "niveau": "Natif"}])

    return data
