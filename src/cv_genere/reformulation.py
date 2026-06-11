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

RÈGLES ABSOLUES ANTI-HALLUCINATION :

1. INTERDICTION ABSOLUE d'inventer des expériences, des entreprises ou des formations.
   Tout ce que tu retournes dans "experiences", "formations", "certifications" et "langues" DOIT être
   directement extrait du texte brut du CV fourni. Si tu ne trouves pas une information, ne l'invente pas.

2. INTERDICTION ABSOLUE de séparer une section regroupée en plusieurs expériences.
   Si le CV brut contient une section type 'EARLIER CAREER', 'ANTERIORITÉ', 'OTHER EXPERIENCES'
   ou similaire avec plusieurs intitulés sous une même entête de dates, tu DOIS la traiter comme
   UNE SEULE expérience avec un champ 'postes' contenant la liste des intitulés. NE PAS SÉPARER.

3. INTERDICTION ABSOLUE d'inventer une description.
   Si une expérience n'a pas de description dans le CV brut (juste un intitulé),
   laisse "description": null. N'utilise que les notes_experiences fournies par l'utilisateur
   ou le CV brut comme source de contenu."""

PROMPT_UTILISATEUR = """Tu dois produire un CV anonymisé et ciblé pour un cabinet de conseil en recrutement.

====== TEXTE BRUT DU CV (SOURCE DE VÉRITÉ) ======
{texte_brut}
====== FIN DU TEXTE BRUT ======

{bloc_notes_experiences}{bloc_profil_adh}DONNÉES STRUCTURÉES DU CONSULTANT :
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

2. PROFIL :
{instruction_profil}

3. KEY VALUE BULLETS (4 à 5 bullet points) :
   Liste 4-5 points forts du consultant SPÉCIFIQUES À L'OFFRE CIBLE.
   Format : phrases courtes et affirmatives (10-20 mots max chacune).
   Source : tu peux paraphraser à partir du CV brut et des notes_experiences (si fournies).
   TU NE PEUX PAS INVENTER de réalisations absentes du CV ou des notes_experiences.

4. COMPÉTENCES : sélectionne et ordonne les 6 compétences les plus pertinentes pour l'offre parmi celles du CV.

5. EXPÉRIENCES : extrais TOUTES les expériences du texte brut.
   - REGROUPEMENTS : si une section regroupe plusieurs postes sous une même entête de dates
     (ex: EARLIER CAREER 2013-2018, ANTERIORITÉ, etc.), tu DOIS la rendre comme UNE SEULE expérience
     avec un champ "postes" contenant la liste des intitulés. NE PAS séparer en plusieurs expériences.
   - EXPÉRIENCES INDIVIDUELLES : pour chaque expérience normale, "postes" est null.
   - Marque 2 ou 3 expériences maximum avec "a_mettre_en_avant": true (les plus pertinentes pour cette offre).
   - Toutes les autres ont "a_mettre_en_avant": false.
   - Description : copie ou paraphrase fidèle du CV brut. Si pas de description disponible,
     mets "description": null. NE PAS INVENTER.

6. FORMATIONS, CERTIFICATIONS, LANGUES : copie-les fidèlement depuis le texte brut, sans omission.

LANGUE DE RÉDACTION :
{langue_instruction}

Retourne UNIQUEMENT ce JSON (aucun texte avant ou après) :
{{
  "profil": "Texte du profil OU null si profil_adh fourni",
  "key_value_bullets": [
    "Point fort #1 spécifique à l'offre.",
    "Point fort #2 spécifique à l'offre.",
    "Point fort #3 spécifique à l'offre.",
    "Point fort #4 spécifique à l'offre."
  ],
  "competences_top6_ordonnees": ["compétence1", "compétence2", "compétence3", "compétence4", "compétence5", "compétence6"],
  "experiences": [
    {{
      "intitule": "Titre exact du poste",
      "entreprise": "Nom réel de l'entreprise",
      "dates": "Mois AAAA – Mois AAAA",
      "description": "Description fidèle ou null si absente",
      "postes": null,
      "a_mettre_en_avant": true
    }},
    {{
      "intitule": "EARLIER CAREER (ou titre du regroupement)",
      "entreprise": "Entreprises diverses ou nom commun",
      "dates": "AAAA – AAAA",
      "description": null,
      "postes": ["Poste 1 — Entreprise", "Poste 2 — Entreprise", "Poste 3 — Entreprise"],
      "a_mettre_en_avant": false
    }}
  ],
  "formations": ["Diplôme exact"],
  "certifications": ["Certification exacte"],
  "langues": [{{"nom": "Français", "niveau": "Natif"}}, {{"nom": "Anglais", "niveau": "Professional"}}]
}}"""

_LANGUE_INSTRUCTION = {
    "fr": "Tu DOIS rédiger les champs 'profil' (si généré), 'key_value_bullets' et toutes les 'description' d'expériences en FRANÇAIS.",
    "en": "You MUST write the 'profil' field (if generated), 'key_value_bullets' and all experience 'description' fields in ENGLISH.",
}

_INSTRUCTION_PROFIL_AVEC_ADH = (
    "   Un profil personnalisé a déjà été fourni par l'utilisateur (voir bloc PROFIL ADH ci-dessus).\n"
    "   Tu DOIS retourner \"profil\": null. NE GÉNÈRE PAS de profil."
)

_INSTRUCTION_PROFIL_SANS_ADH = (
    "   Extrais VERBATIM le 1er paragraphe du CV brut (le résumé / executive summary placé au début,\n"
    "   AVANT toute section 'EXPERIENCES', 'PROFESSIONAL EXPERIENCE', 'EXECUTIVE VALUE PROPOSITION', etc.).\n"
    "   Copie-le tel quel, sans reformulation, sans traduction.\n"
    "   Si le CV brut n'a PAS de paragraphe initial de résumé, génère 3-4 lignes synthétiques\n"
    "   basées sur titre_courant + années + domaines (sans inventer de détails précis)."
)


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


def reformuler_avec_haiku(cv_data: dict, offre_data: dict, langue: str = "fr") -> dict:
    """Reformule le contenu du CV pour le cibler sur une offre.

    Lit cv_data["texte_brut"] comme source de vérité pour les expériences.
    Si cv_data["profil_adh"] est fourni, Haiku ne génère pas de profil.
    Si cv_data["notes_experiences"] est fourni, Haiku peut s'en servir
    pour enrichir descriptions et key_value_bullets.

    Args:
        cv_data: dict du CV (doit contenir texte_brut).
        offre_data: dict de l'offre cible.
        langue: "fr" ou "en" — langue de rédaction.

    Returns:
        dict avec profil, key_value_bullets, competences_top6_ordonnees,
        experiences, formations, certifications, langues.

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
    profil_adh = (cv_data.get("profil_adh") or "").strip()
    notes_experiences = (cv_data.get("notes_experiences") or "").strip()

    bloc_profil_adh = (
        f"====== PROFIL ADH (fourni par l'utilisateur — à utiliser TEL QUEL côté template) ======\n"
        f"{profil_adh}\n"
        f"====== FIN PROFIL ADH ======\n\n"
        if profil_adh else ""
    )
    bloc_notes_experiences = (
        f"====== NOTES EXPÉRIENCES (additionnelles, fournies par l'utilisateur) ======\n"
        f"{notes_experiences}\n"
        f"====== FIN NOTES EXPÉRIENCES ======\n\n"
        if notes_experiences else ""
    )

    instruction_profil = (
        _INSTRUCTION_PROFIL_AVEC_ADH if profil_adh else _INSTRUCTION_PROFIL_SANS_ADH
    )
    langue_instruction = _LANGUE_INSTRUCTION.get(langue, _LANGUE_INSTRUCTION["fr"])

    prompt = PROMPT_UTILISATEUR.format(
        texte_brut=texte_brut[:8000] if texte_brut else "(texte brut non disponible)",
        bloc_profil_adh=bloc_profil_adh,
        bloc_notes_experiences=bloc_notes_experiences,
        instruction_profil=instruction_profil,
        titre_courant=cv_data.get("titre_courant") or "Consultant IT",
        annees_experience=cv_data.get("annees_experience") or "N/A",
        competences=", ".join(competences[:20]) if competences else "Non précisé",
        domaines=", ".join(domaines[:10]) if domaines else "Non précisé",
        offre_titre=offre_data.get("titre") or "",
        offre_entreprise=offre_data.get("entreprise") or "Non précisé",
        offre_description=(offre_data.get("description") or "")[:2000],
        langue_instruction=langue_instruction,
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
    data.setdefault("profil", "")
    data.setdefault("key_value_bullets", [])
    data.setdefault("competences_top6_ordonnees", competences[:6])
    data.setdefault("experiences", [])
    data.setdefault("formations", [])
    data.setdefault("certifications", [])
    data.setdefault("langues", [{"nom": "Français", "niveau": "Natif"}])

    return data
