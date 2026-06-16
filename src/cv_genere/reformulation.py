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
   laisse "description_bullets": null. N'utilise que les notes_experiences fournies
   par l'utilisateur ou le CV brut comme source de contenu.

4. INTERDICTION ABSOLUE d'omettre un sous-projet présent dans le CV brut ou les notes_experiences.
   Si une expérience contient plusieurs sous-projets distincts (titres intermédiaires, paragraphes
   séparés), tu DOIS TOUS les préserver dans description_bullets avec un en-tête **Sous-projet**."""

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

5. EXPÉRIENCES À METTRE EN AVANT :
   Tu DOIS marquer entre 2 et 3 expériences avec "a_mettre_en_avant": true. PAS MOINS DE 2.
   Choisis celles dont l'intitulé ou la description contient des mots-clés directement liés à l'offre cible.
   Exemple pour une offre TRADING : marque les expériences contenant 'Trade', 'Finance', 'Trading',
   'DOKA', 'Banking', 'Capital Markets' dans l'intitulé ou la description.
   Si AUCUNE expérience ne semble parfaitement pertinente, marque quand même les 2 plus récentes
   ou les 2 ayant le plus de mots-clés communs avec l'offre.

6. REGROUPEMENT EARLIER CAREER :
   Si le CV brut contient une section regroupée (ex: 'EARLIER CAREER 2013-2018') avec plusieurs intitulés,
   et que notes_experiences contient les DÉTAILS d'au moins UNE de ces missions, alors :
   - Les missions DÉTAILLÉES dans notes_experiences sont remontées comme expériences INDIVIDUELLES
     (avec leur vraie période, leurs description_bullets).
   - Les missions NON DÉTAILLÉES (juste intitulées dans le CV brut, sans notes) restent regroupées
     dans UN bloc Earlier Career résiduel avec :
     * la période RÉSIDUELLE (recalculée selon les missions restantes — pas la période totale du bloc)
     * "postes": liste des intitulés restants
     * "description_bullets": null
   - Si TOUTES les missions du bloc ont été détaillées, NE PAS produire de bloc Earlier Career résiduel.
   - NE JAMAIS afficher la même mission DEUX FOIS (une fois en expérience individuelle ET dans Earlier Career).

7. FORMAT DES DESCRIPTIONS :
   Tu DOIS retourner les descriptions sous forme de "description_bullets" (liste de strings courts),
   JAMAIS sous forme de paragraphe long.
   Chaque bullet :
   - Commence par un VERBE D'ACTION (Led, Coordinated, Managed, Defined, Drove, Implemented, etc.).
   - Fait 10-25 mots maximum.
   - Représente UNE action ou responsabilité distincte.
   Si la source (CV brut ou notes_experiences) contient déjà des bullets, conserve leur structure
   (un bullet source = un bullet output). Si la source contient un paragraphe dense, découpe-le en
   3-6 bullets logiques.

8. SOUS-PROJETS DANS UNE EXPÉRIENCE :
   Si une expérience contient PLUSIEURS sous-projets dans la source (CV brut ou notes_experiences),
   séparés par des titres intermédiaires ou des paragraphes distincts (ex: 'SAB AT migration' puis
   'DOKA-NG Trade Finance'), tu DOIS PRÉSERVER ces sous-blocs distinctement.
   Chaque sous-projet commence par un bullet titre au format markdown **Nom du sous-projet**.
   NE JAMAIS fusionner deux sous-projets. NE JAMAIS omettre un sous-projet.

   Exemple — si les notes_experiences disent :
     "SAB AT migration: bullet1, bullet2, bullet3
      DOKA-NG implementation: bullet4, bullet5, bullet6"
   Tu DOIS retourner :
     "description_bullets": [
       "**SAB AT Migration**",
       "bullet1",
       "bullet2",
       "bullet3",
       "**DOKA-NG Trade Finance Implementation**",
       "bullet4",
       "bullet5",
       "bullet6"
     ]

9. FORMATIONS, CERTIFICATIONS, LANGUES : copie-les fidèlement depuis le texte brut, sans omission.

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
      "description_bullets": ["Bullet 1", "Bullet 2", "Bullet 3"],
      "postes": null,
      "a_mettre_en_avant": true
    }},
    {{
      "intitule": "Titre du poste",
      "entreprise": "Entreprise",
      "dates": "AAAA – AAAA",
      "description_bullets": ["**SAB AT Migration**", "Bullet 1", "Bullet 2", "**DOKA-NG Trade Finance**", "Bullet 3", "Bullet 4"],
      "postes": null,
      "a_mettre_en_avant": true
    }},
    {{
      "intitule": "Earlier Career (ou titre du regroupement)",
      "entreprise": "Entreprises diverses ou nom commun",
      "dates": "AAAA – AAAA",
      "description_bullets": null,
      "postes": ["Poste 1 — Entreprise", "Poste 2 — Entreprise"],
      "a_mettre_en_avant": false
    }}
  ],
  "formations": ["Diplôme exact"],
  "certifications": ["Certification exacte"],
  "langues": [{{"nom": "Français", "niveau": "Natif"}}, {{"nom": "Anglais", "niveau": "Professional"}}]
}}"""

_LANGUE_INSTRUCTION = {
    "fr": "Tu DOIS rédiger les champs 'profil' (si généré), 'key_value_bullets' et tous les 'description_bullets' d'expériences en FRANÇAIS.",
    "en": "You MUST write the 'profil' field (if generated), 'key_value_bullets' and all experience 'description_bullets' in ENGLISH.",
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


def reformuler_avec_haiku(cv_data: dict, offre_data: dict, langue: str = "fr", instructions_supplementaires: str = "") -> dict:
    """Reformule le contenu du CV pour le cibler sur une offre.

    Lit cv_data["texte_brut"] comme source de vérité pour les expériences.
    Si cv_data["profil_adh"] est fourni, Haiku ne génère pas de profil.
    Si cv_data["notes_experiences"] est fourni, Haiku peut s'en servir
    pour enrichir descriptions et key_value_bullets, et remonter des
    missions détaillées hors d'un bloc Earlier Career.

    Args:
        cv_data: dict du CV (doit contenir texte_brut).
        offre_data: dict de l'offre cible.
        langue: "fr" ou "en" — langue de rédaction.

    Returns:
        dict avec profil, key_value_bullets, competences_top6_ordonnees,
        experiences (chacune avec description_bullets + postes optionnels),
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

    if instructions_supplementaires.strip():
        prompt += (
            "\n\nINSTRUCTIONS SUPPLÉMENTAIRES DE L'OPÉRATEUR (à respecter sauf contradiction "
            "avec les règles anti-hallucination ci-dessus) :\n"
            + instructions_supplementaires.strip()
            + "\n"
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

    # Normaliser les expériences : garantir description_bullets et postes
    for exp in data.get("experiences", []):
        exp.setdefault("description_bullets", None)
        exp.setdefault("postes", None)
        exp.setdefault("a_mettre_en_avant", False)

    return data
