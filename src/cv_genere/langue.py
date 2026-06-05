"""Détection de la langue d'un texte CV et labels de template bilingues."""

_EN_MOTS = frozenset({
    "the", "and", "of", "with", "for", "by", "in", "at", "to", "from",
    "on", "is", "are", "was", "were", "has", "have", "been", "as", "an",
})
_FR_MOTS = frozenset({
    "le", "la", "et", "de", "du", "avec", "pour", "par", "en", "les",
    "des", "un", "une", "dans", "sur", "au", "aux", "il", "elle", "nous",
})

LABELS_FR: dict[str, str] = {
    "candidature_pour": "Candidature pour",
    "contact":          "Contact",
    "email":            "Email",
    "telephone":        "Téléphone",
    "competences_cles": "Compétences clés",
    "formation":        "Formation",
    "certifications":   "Certifications",
    "secteurs":         "Secteurs",
    "langues":          "Langues",
    "profil":           "Profil",
    "experiences":      "Expériences",
    "annees_experience": "{n} ans d'expérience",
}

LABELS_EN: dict[str, str] = {
    "candidature_pour": "Applying for",
    "contact":          "Contact",
    "email":            "Email",
    "telephone":        "Phone",
    "competences_cles": "Key Skills",
    "formation":        "Education",
    "certifications":   "Certifications",
    "secteurs":         "Industries",
    "langues":          "Languages",
    "profil":           "Profile",
    "experiences":      "Experiences",
    "annees_experience": "{n} years of experience",
}


def detecter_langue_cv(texte: str) -> str:
    """Détecte la langue du texte brut du CV.

    Compte les occurrences de mots fréquents EN vs FR.
    Défaut 'fr' si total < 10 mots détectés ou égalité.

    Returns:
        "en" ou "fr"
    """
    if not texte:
        return "fr"
    mots = texte.lower().split()
    count_en = sum(1 for m in mots if m in _EN_MOTS)
    count_fr = sum(1 for m in mots if m in _FR_MOTS)
    total = count_en + count_fr
    if total < 5:
        return "fr"
    return "en" if count_en > count_fr else "fr"


def get_labels(langue: str) -> dict[str, str]:
    """Retourne le dict de labels de template pour la langue donnée."""
    return LABELS_EN if langue == "en" else LABELS_FR
