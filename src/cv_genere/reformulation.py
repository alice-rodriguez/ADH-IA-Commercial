"""Reformulation du contenu CV par Haiku pour l'adapter à une offre cible."""
import json
import logging
import os

from anthropic import Anthropic

logger = logging.getLogger(__name__)

MODELE = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

PROMPT_SYSTEME = """Tu es un assistant RH expert en recrutement IT qui prépare des CVs anonymisés pour un cabinet de conseil.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans préambule, sans commentaire.

RÈGLE ABSOLUE ANTI-HALLUCINATION :
INTERDICTION ABSOLUE d'inventer des expériences, des entreprises ou des formations.
Tout ce que tu retournes dans "experiences", "formations", "certifications" et "langues" DOIT être
directement extrait du texte brut du CV fourni. Si tu ne trouves pas une information, ne l'invente pas."""

PROMPT_UTILISATEUR = """Tu dois créer un CV anonymisé et ciblé pour un cabinet de conseil en recrutement.

====== TEXTE BRUT DU CV (SOURCE DE VÉRITÉ) ======
{texte_brut}
====== FIN DU TEXTE BRUT ======

DONNÉES STRUCTURÉES DU CONSULTANT :
- Titre actuel : {titre_courant}
- Expérience : {annees_experience} ans
- Compétences déclarées : {competences}
- Domaines : {domaines}

OFFRE CIBLE :
- Titre : {offre_titre}
- Entreprise : {offre_entreprise}
- Description : {offre_description}

INSTRUCTIONS :
1. ANONYMISATION : l'anonymisation ne concerne QUE le candidat lui-même (nom, email, téléphone, adresse personnelle).
   Garde les vrais noms d'employeurs (AG2R, HSBC, Crédit Agricole, etc.) — ils ne sont PAS anonymisés.
2. PROFIL : rédige 4-5 lignes qui mettent en valeur le consultant pour CETTE offre spécifique.
3. COMPÉTENCES : sélectionne et ordonne les 6 compétences les plus pertinentes pour l'offre parmi celles du CV.
4. EXPÉRIENCES : extrais TOUTES les expériences du texte brut (intitulé réel, entreprise réelle, dates réelles).
   - Marque 2 ou 3 expériences maximum avec "a_mettre_en_avant": true (les plus pertinentes pour cette offre).
   - Toutes les autres ont "a_mettre_en_avant": false.
   - Tu peux reformuler la description pour valoriser ce qui est pertinent pour l'offre,
     mais SANS inventer de chiffres ou de réalisations absents du CV.
5. FORMATIONS, CERTIFICATIONS, LANGUES : copie-les fidèlement depuis le texte brut, sans omission.

INTERDICTION ABSOLUE D'INVENTER DES EXPÉRIENCES OU ENTREPRISES.
Toute expérience que tu retournes DOIT être présente dans le texte brut ci-dessus.
Si tu ne trouves pas une expérience dans le texte brut, ne l'ajoute pas. JAMAIS D'INVENTION.

Retourne UNIQUEMENT ce JSON (aucun texte avant ou après) :
{{
  "profil_reformule": "4-5 lignes adaptées à l'offre cible.",
  "competences_top6_ordonnees": ["compétence1", "compétence2", "compétence3", "compétence4", "compétence5", "compétence6"],
  "experiences": [
    {{
      "intitule": "Titre exact du poste tel qu'il apparaît dans le CV",
      "entreprise": "Nom réel de l'entreprise (ex: AG2R LA MONDIALE, HSBC Continental Europe, etc.)",
      "dates": "Mois AAAA – Mois AAAA",
      "description": "Description fidèle au CV, reformulée pour valoriser les points pertinents pour l'offre.",
      "a_mettre_en_avant": true
    }},
    {{
      "intitule": "Titre exact du poste",
      "entreprise": "Nom réel de l'entreprise",
      "dates": "AAAA – AAAA",
      "description": "Description.",
      "a_mettre_en_avant": false
    }}
  ],
  "formations": ["Diplôme exact tel qu'il apparaît dans le CV"],
  "certifications": ["Certification exacte telle qu'elle apparaît dans le CV"],
  "langues": [{{"nom": "Français", "niveau": "Natif"}}, {{"nom": "Anglais", "niveau": "Professional"}}]
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

    Lit cv_data["texte_brut"] comme source de vérité pour les expériences.

    Returns:
        dict avec profil_reformule, competences_top6_ordonnees, experiences,
        formations, certifications, langues.

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

    texte_brut = (cv_data.get("texte_brut") or "").strip()

    prompt = PROMPT_UTILISATEUR.format(
        texte_brut=texte_brut[:8000] if texte_brut else "(texte brut non disponible)",
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
    data.setdefault("competences_top6_ordonnees", competences[:6])
    data.setdefault("experiences", [])
    data.setdefault("formations", [])
    data.setdefault("certifications", [])
    data.setdefault("langues", [{"nom": "Français", "niveau": "Natif"}])

    return data
