"""
Parsing de montants financiers (TJM et salaire) depuis des textes bruts.

Fonctions pures, sans effet de bord, sans dépendances externes.
Appelées par les collectors (sous-étape A.3) pour peupler les champs
tjm_min/tjm_max et salaire_min/salaire_max de la table offres.

Plages de validité (garde-fous contre valeurs aberrantes) :
    TJM     : 100 à 2 000 €/jour
    Salaire : 15 000 à 300 000 €/an

Contrat strict (évite les faux positifs sur du texte libre) :
    parse_tjm    ne reconnaît un montant QUE s'il est accompagné
                 d'un préfixe TJM explicite (TJM, tarif journalier,
                 taux journalier, rate) OU d'un suffixe journalier
                 (/j, /jr, /jour, /day, par jour, HT/j, HT/jour).
    parse_salaire ne reconnaît un montant QUE si le suffixe k/K
                 est présent, OU si un préfixe salaire explicite
                 (salaire, rémunération, package) précède le nombre,
                 OU si un suffixe annuel (/an, /year, par an, annuel,
                 brut annuel) suit le montant.
    Sans signal explicite → (None, None) dans les deux cas.
"""

import re

TJM_MIN_VALIDE = 100
TJM_MAX_VALIDE = 2000
SALAIRE_MIN_VALIDE = 15_000
SALAIRE_MAX_VALIDE = 300_000

# ── Regex compilées au niveau du module (une seule fois) ──────────────────────

# TJM — préfixe obligatoire : TJM, tarif journalier, taux journalier, rate
# Ex : "TJM : 450 €", "Tarif journalier : 450-900 €", "Rate: 600 €"
_RE_TJM_PREFIXE = re.compile(
    r'(?:tjm|tarif\s+journalier|taux\s+journalier|rate)'
    r'\s*:?\s*'
    r'(\d+)'
    r'(?:\s*[-–]\s*(\d+))?'
    r'\s*€',
    re.IGNORECASE,
)

# TJM — suffixe obligatoire : /j, /jr, /jour, /day, par jour, HT/j, HT/jour
# Ex : "450 €/jour", "450 € HT/j", "600 €/day", "450 € par jour"
_RE_TJM_SUFFIXE = re.compile(
    r'(\d+)'
    r'(?:\s*[-–]\s*(\d+))?'
    r'\s*€\s*'
    r'(?:(?:ht\s*)?/\s*(?:j(?:r|our)?|day)|par\s+jour)',
    re.IGNORECASE,
)

# Salaire — suffixe k/K (signal intrinsèque suffisant)
# Ex : "65k €", "65k-70k €", "65 k - 70 k", "Salaire : 65k"
_RE_SAL_K = re.compile(
    r'(?:salaire\s*:?\s*)?'
    r'(\d+)\s*[kK]'
    r'(?:\s*[-–]\s*(\d+)\s*[kK])?'
    r'\s*€?',
    re.IGNORECASE,
)

# Salaire — préfixe obligatoire : salaire, rémunération, package
# Ex : "Salaire : 45000 €", "Rémunération : 50000 €", "Package 70000 €"
_RE_SAL_NUM_PREFIXE = re.compile(
    r'(?:salaire|r[eé]mun[eé]ration|package)'
    r'\s*:?\s*'
    r'(\d{4,6})'
    r'(?:\s*[-–]\s*(\d{4,6}))?'
    r'\s*€?',
    re.IGNORECASE,
)

# Salaire — suffixe annuel obligatoire : /an, /year, par an, annuel, brut annuel
# Ex : "60000 €/an", "45000 € brut annuel", "50000/year"
_RE_SAL_NUM_SUFFIXE = re.compile(
    r'(\d{4,6})'
    r'(?:\s*[-–]\s*(\d{4,6}))?'
    r'\s*€?\s*'
    r'(?:/\s*(?:an|year)|par\s+an|(?:brut\s+)?annuel)',
    re.IGNORECASE,
)


def _normaliser(texte: str | None) -> str:
    """
    Prépare un texte pour le parsing :
      - espaces insécables (\\xa0) → espaces normaux
      - formatage français des nombres ("45 000" → "45000")
    Deux passes pour couvrir jusqu'à 9 chiffres ("1 234 567" → "1234567").
    """
    if not texte:
        return ""
    texte = texte.replace("\xa0", " ")
    texte = re.sub(r'(\d) (\d{3})(?!\d)', r'\1\2', texte)
    texte = re.sub(r'(\d) (\d{3})(?!\d)', r'\1\2', texte)
    return texte


def _valider_plage(
    val_min: int, val_max: int, borne_min: int, borne_max: int
) -> tuple[int | None, int | None]:
    """Retourne (None, None) si min > max ou si une valeur est hors bornes."""
    if val_min > val_max:
        return None, None
    if val_min < borne_min or val_max > borne_max:
        return None, None
    return val_min, val_max


def _extraire(m: re.Match, multiplicateur: int = 1) -> tuple[int, int] | None:
    """Extrait (min, max) depuis un match avec groupes 1 et 2."""
    try:
        val_min = int(m.group(1)) * multiplicateur
        val_max = int(m.group(2)) * multiplicateur if m.group(2) else val_min
        return val_min, val_max
    except (ValueError, TypeError):
        return None


def parse_tjm(texte: str | None) -> tuple[int | None, int | None]:
    """
    Extrait un TJM depuis un texte brut.

    Ne reconnaît un montant QUE s'il est accompagné d'un signal explicite :
      - préfixe : TJM, tarif journalier, taux journalier, rate
      - suffixe : /j, /jr, /jour, /day, par jour, HT/j, HT/jour
    Sans signal → (None, None), pour éviter les faux positifs sur texte libre.

    Retourne (tjm_min, tjm_max) en €/jour, ou (None, None) si :
      - aucun signal explicite détecté
      - valeur hors plage [100, 2 000]
      - min > max
    """
    normalise = _normaliser(texte)
    if not normalise:
        return None, None

    for pattern in (_RE_TJM_PREFIXE, _RE_TJM_SUFFIXE):
        m = pattern.search(normalise)
        if m:
            vals = _extraire(m)
            if vals is None:
                continue
            return _valider_plage(vals[0], vals[1], TJM_MIN_VALIDE, TJM_MAX_VALIDE)

    return None, None


def parse_salaire(texte: str | None) -> tuple[int | None, int | None]:
    """
    Extrait un salaire annuel depuis un texte brut.

    Ne reconnaît un montant QUE s'il est accompagné d'un signal explicite :
      - suffixe k/K (65k, 70K) — signal intrinsèque suffisant
      - préfixe : salaire, rémunération, package
      - suffixe : /an, /year, par an, annuel, brut annuel
    Sans signal → (None, None), pour éviter les faux positifs sur texte libre.

    Retourne (sal_min, sal_max) en €/an, ou (None, None) si :
      - aucun signal explicite détecté
      - valeur hors plage [15 000, 300 000]
      - min > max
    """
    normalise = _normaliser(texte)
    if not normalise:
        return None, None

    # Format k/K : signal intrinsèque, priorité absolue
    m = _RE_SAL_K.search(normalise)
    if m:
        vals = _extraire(m, multiplicateur=1000)
        if vals is not None:
            return _valider_plage(vals[0], vals[1], SALAIRE_MIN_VALIDE, SALAIRE_MAX_VALIDE)

    # Grands nombres avec préfixe ou suffixe explicite
    for pattern in (_RE_SAL_NUM_PREFIXE, _RE_SAL_NUM_SUFFIXE):
        m = pattern.search(normalise)
        if m:
            vals = _extraire(m)
            if vals is None:
                continue
            return _valider_plage(vals[0], vals[1], SALAIRE_MIN_VALIDE, SALAIRE_MAX_VALIDE)

    return None, None
