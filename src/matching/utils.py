"""Utilitaires de normalisation et comparaison pour le matching."""

import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normaliser(s: str) -> str:
    """Lowercase + suppr. accents + / et - → '' + espaces normalisés."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("/", "").replace("-", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normaliser_lieu(s: str) -> str:
    """Lowercase + suppr. accents + / et - → espace + espaces normalisés."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("/", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Variantes domaines métier
# ---------------------------------------------------------------------------

VARIANTES_DOMAINES: dict[str, list[str]] = {
    "banque": ["banque", "bank", "bancaire", "finance", "financier", "assetsmanagement",
               "bfi", "marches financiers", "capital markets"],
    "assurance": ["assurance", "insurance", "mutuelle", "prevoyance", "retraite"],
    "energie": ["energie", "energy", "utilities", "electricite", "gaz", "petrol",
                "petrole", "renouvelable"],
    "telecom": ["telecom", "telecommunication", "telecommunications", "telco",
                "operateur", "mobile", "internet"],
    "industrie": ["industrie", "industrie manufacturiere", "manufacturing", "automobile",
                  "aeronautique", "aerospatial", "defense", "chimie", "pharmacie"],
    "retail": ["retail", "distribution", "grande distribution", "commerce", "ecommerce",
               "luxe", "mode"],
    "public": ["public", "secteur public", "administration", "etat", "collectivite",
               "ministere", "hopital", "sante publique"],
    "sante": ["sante", "health", "healthcare", "medecine", "medical", "pharma",
              "biotechnologie", "biotech"],
    "transport": ["transport", "logistique", "supply chain", "shipping", "fret",
                  "ferroviaire", "aviation"],
}


def _domaines_cv_normalises(domaines_cv: list[str]) -> set[str]:
    """Retourne les clés VARIANTES_DOMAINES couvertes par les domaines du CV."""
    norms = {normaliser(d) for d in domaines_cv}
    couvertes: set[str] = set()
    for cle, variantes in VARIANTES_DOMAINES.items():
        for v in variantes:
            if v in norms or any(v in n for n in norms):
                couvertes.add(cle)
                break
    return couvertes


# ---------------------------------------------------------------------------
# Extraction années d'expérience requises dans le texte d'une offre
# ---------------------------------------------------------------------------

_RE_ANNEES = re.compile(
    r"(\d{1,2})\s*(?:a\s*\d{1,2}\s*)?ans?\s*"
    r"(?:d[e']?\s*)?(?:experience|minimum|min\.?|requis)",
    re.IGNORECASE,
)


def extraire_annees_requises(texte: str) -> Optional[int]:
    """Extrait le nombre d'années d'expérience requis dans un texte d'offre.

    Returns:
        Premier entier trouvé ou None.
    """
    texte_norm = normaliser(texte).replace("'", "")
    m = _RE_ANNEES.search(texte_norm)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Proximité géographique
# ---------------------------------------------------------------------------

_IDF_MOTS = {
    "paris", "idf", "ile de france", "ile-de-france", "essonne", "hauts de seine",
    "seine saint denis", "val de marne", "val d oise", "yvelines", "seine et marne",
    "seine-et-marne", "la defense", "boulogne", "issy", "courbevoie", "levallois",
    "neuilly", "clichy", "nanterre", "vincennes", "saint denis", "montreuil",
    "puteaux", "velizy", "massy", "saclay",
}


def _est_idf(lieu_norm: str) -> bool:
    return any(mot in lieu_norm for mot in _IDF_MOTS)


def lieu_proche(lieu_cv: str, lieu_offre: str) -> int:
    """Score géographique entre 0 et 100.

    100 : correspondance directe ou remote universel
     75 : les deux sont en IDF
     50 : correspondance partielle
      0 : aucun lien
    """
    if not lieu_cv or not lieu_offre:
        return 50

    cv = _normaliser_lieu(lieu_cv)
    offre = _normaliser_lieu(lieu_offre)

    if "remote" in offre or "teletravail" in offre or "teletravail" in cv:
        return 100

    if cv in offre or offre in cv:
        return 100

    if _est_idf(cv) and _est_idf(offre):
        return 75

    cv_mots = set(cv.split())
    offre_mots = set(offre.split())
    if cv_mots & offre_mots:
        return 50

    return 0
