"""Zones géographiques pour le score de lieu (MATCH-01).

On raisonne par DÉPARTEMENT et par RÉGION, jamais par égalité de chaînes :
  - « Cergy » (95) et « Vélizy-Villacoublay (78) » sont deux communes d'Île-de-France ;
  - « IDF », « Paris/IDF », « Île-de-France », « région parisienne » couvrent les
    départements 75, 77, 78, 91, 92, 93, 94, 95.

zones(texte) renvoie l'ensemble des départements reconnus dans un texte de lieu
(code postal, numéro entre parenthèses, nom de département, de région ou de commune).
Ensemble vide = lieu inconnu (le score de lieu est alors NEUTRE).
"""

import re
import unicodedata

IDF = frozenset({"75", "77", "78", "91", "92", "93", "94", "95"})

# Régions métropolitaines → départements
REGIONS: dict[str, frozenset[str]] = {
    "ile de france": IDF,
    "auvergne rhone alpes": frozenset({"01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"}),
    "bourgogne franche comte": frozenset({"21", "25", "39", "58", "70", "71", "89", "90"}),
    "bretagne": frozenset({"22", "29", "35", "56"}),
    "centre val de loire": frozenset({"18", "28", "36", "37", "41", "45"}),
    "corse": frozenset({"2A", "2B"}),
    "grand est": frozenset({"08", "10", "51", "52", "54", "55", "57", "67", "68", "88"}),
    "hauts de france": frozenset({"02", "59", "60", "62", "80"}),
    "normandie": frozenset({"14", "27", "50", "61", "76"}),
    "nouvelle aquitaine": frozenset({"16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"}),
    "occitanie": frozenset({"09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"}),
    "pays de la loire": frozenset({"44", "49", "53", "72", "85"}),
    "provence alpes cote d azur": frozenset({"04", "05", "06", "13", "83", "84"}),
}
REGION_DE = {dep: nom for nom, deps in REGIONS.items() for dep in deps}

# Expressions qui désignent toute l'Île-de-France
_IDF_EXPRESSIONS = ("ile de france", "idf", "region parisienne", "paris idf", "paris et idf", "grand paris")

# Mobilité nationale : couvre tous les départements
# (jamais « france » seul : il apparaît dans « Île-de-France » et « Hauts-de-France »)
_FRANCE_EXPRESSIONS = ("toute la france", "france entiere", "mobilite nationale", "mobilite france",
                       "partout en france", "france metropolitaine", "national")

# Départements (noms) et communes fréquentes → département
_NOMS: dict[str, str] = {
    # Île-de-France : départements
    "paris": "75", "seine et marne": "77", "yvelines": "78", "essonne": "91", "hauts de seine": "92",
    "seine saint denis": "93", "val de marne": "94", "val d oise": "95",
    # Île-de-France : communes et pôles d'emploi
    "la defense": "92", "courbevoie": "92", "puteaux": "92", "nanterre": "92", "boulogne": "92",
    "boulogne billancourt": "92", "issy les moulineaux": "92", "issy": "92", "levallois": "92",
    "levallois perret": "92", "neuilly": "92", "clichy": "92", "rueil malmaison": "92", "suresnes": "92",
    "montrouge": "92", "chatillon": "92", "clamart": "92", "colombes": "92", "gennevilliers": "92",
    "saint denis": "93", "montreuil": "93", "noisy le grand": "93", "bobigny": "93", "pantin": "93",
    "aubervilliers": "93", "saint ouen": "93", "roissy": "95", "cergy": "95", "cergy pontoise": "95",
    "pontoise": "95", "argenteuil": "95", "sarcelles": "95", "creteil": "94", "vincennes": "94",
    "ivry sur seine": "94", "ivry": "94", "vitry sur seine": "94", "rungis": "94", "charenton": "94",
    "fontenay sous bois": "94", "velizy": "78", "velizy villacoublay": "78", "versailles": "78",
    "saint quentin en yvelines": "78", "guyancourt": "78", "montigny le bretonneux": "78",
    "saint germain en laye": "78", "poissy": "78", "massy": "91", "saclay": "91", "evry": "91",
    "les ulis": "91", "palaiseau": "91", "orsay": "91", "courcouronnes": "91", "marne la vallee": "77",
    "melun": "77", "meaux": "77", "serris": "77", "chessy": "77",
    # Grandes villes hors Île-de-France
    "lyon": "69", "villeurbanne": "69", "marseille": "13", "aix en provence": "13", "lille": "59",
    "toulouse": "31", "bordeaux": "33", "nantes": "44", "rennes": "35", "strasbourg": "67",
    "nice": "06", "sophia antipolis": "06", "montpellier": "34", "grenoble": "38", "rouen": "76",
    "tours": "37", "orleans": "45", "niort": "79", "dijon": "21", "metz": "57", "nancy": "54",
    "clermont ferrand": "63", "saint etienne": "42", "le mans": "72", "angers": "49", "brest": "29",
    "caen": "14", "reims": "51", "amiens": "80", "limoges": "87", "poitiers": "86", "pau": "64",
    "annecy": "74", "toulon": "83", "avignon": "84", "le havre": "76", "valence": "26",
}
# Noms de région seuls (« Auvergne-Rhône-Alpes », « Hauts-de-France »…)
_NOMS_REGIONS = {nom: deps for nom, deps in REGIONS.items() if nom != "ile de france"}

_TELETRAVAIL = ("teletravail", "remote", "full remote", "a distance", "home office")


def normaliser_lieu(texte: str) -> str:
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return f" {texte.strip()} "          # bornes pour chercher des mots entiers


def _contient(norm: str, expression: str) -> bool:
    return f" {expression} " in norm


def mentionne_teletravail(texte: str) -> bool:
    norm = normaliser_lieu(texte)
    return any(_contient(norm, t) for t in _TELETRAVAIL)


def zones(texte: str) -> frozenset[str]:
    """Départements désignés par un texte de lieu. Vide si rien n'est reconnu."""
    if not texte:
        return frozenset()
    norm = normaliser_lieu(texte)
    trouves: set[str] = set()
    if any(_contient(norm, e) for e in _IDF_EXPRESSIONS):
        trouves |= IDF
    if any(_contient(norm, e) for e in _FRANCE_EXPRESSIONS):
        trouves |= set(REGION_DE)
    for nom, deps in _NOMS_REGIONS.items():
        if _contient(norm, nom):
            trouves |= deps
    for nom, dep in _NOMS.items():
        if _contient(norm, nom):
            trouves.add(dep)
    # Codes postaux (75008, 92100…) et numéros de département entre parenthèses « (78) »
    for cp in re.findall(r"(?<!\d)(\d{5})(?!\d)", texte or ""):
        dep = cp[:2]
        if dep in REGION_DE:
            trouves.add(dep)
    for dep in re.findall(r"\((\d{2})\)", texte or ""):
        if dep in REGION_DE:
            trouves.add(dep)
    return frozenset(trouves)
