"""Import manuel d'une annonce (MANUEL-01).

Alice colle le texte d'une annonce (ou son lien) repérée hors des sources
scrapées. L'import produit une ligne NORMALE de la table offres, avec
source = "Manuelle" : tout l'aval existant (matching, analyse IA, CV adapté)
fonctionne sans chemin parallèle.

Étapes :
  1. texte : collé par Alice, ou lu sur la page (requête simple, sans aucun
     contournement de protection anti-robot)
  2. structuration en un appel Haiku (JSON strict, champ absent → null)
     échec → l'offre est enregistrée quand même, champs à compléter à la main
  3. enregistrement (même hash que les autres sources ; si déjà présente :
     mise à jour de la ligne existante, pas de doublon)
  4. matching immédiat de cette offre contre les CVs profilés

Une offre manuelle ne passe ni par le pré-filtre ni par le filtre IA du
pipeline : elle est insérée ici directement, jamais écartée.
"""

import json
import logging
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from src.storage import database

logger = logging.getLogger(__name__)

SOURCE_MANUELLE = "Manuelle"
LONGUEUR_MIN_PAGE = 200
TIMEOUT_PAGE = 15
LONGUEUR_TITRE_SECOURS = 120
MAX_TEXTE_HAIKU = 12000

MESSAGE_PAGE_ILLISIBLE = (
    "Impossible de lire cette page automatiquement. Copiez le texte de l'annonce "
    "et collez-le dans l'onglet Texte."
)
MESSAGE_SAISIE_VIDE = "Indiquez le texte de l'annonce ou son lien (URL)."
MESSAGE_URL_INVALIDE = "Le lien doit commencer par http:// ou https://."

HEADERS_PAGE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

TYPES_CONTRAT = ["CDI", "CDD", "Freelance", "Mission", "Appel d'offres", "Intérim"]

PROMPT_STRUCTURATION = """Tu extrais les informations d'une annonce d'emploi ou de mission.
Réponds UNIQUEMENT avec un objet JSON (sans markdown, sans explication), de la forme :
{
  "titre": "<intitulé du poste ou de la mission>",
  "entreprise": "<entreprise, client ou acheteur>",
  "lieu": "<ville, département ou région>",
  "type_contrat": "<un parmi : CDI, CDD, Freelance, Mission, Appel d'offres, Intérim>",
  "tjm_min": <entier en euros par jour>,
  "tjm_max": <entier en euros par jour>,
  "description": "<texte de l'annonce nettoyé>"
}

Règles :
- Tout champ absent de l'annonce vaut null. N'invente JAMAIS une valeur.
- tjm_min / tjm_max : uniquement un tarif JOURNALIER explicite. Un TJM unique
  donne tjm_min = tjm_max. Un salaire annuel n'est pas un TJM : null.
- description : le texte de l'annonce, débarrassé des menus, boutons, mentions
  de cookies et répétitions, sans résumer ni reformuler le contenu utile.

ANNONCE :
"""


class ImportManuelErreur(Exception):
    """Saisie refusée : le message est destiné à Alice, tel quel (HTTP 422)."""


# ── 1. Texte ─────────────────────────────────────────────────────────────────

def recuperer_texte_page(url: str) -> str:
    """Lecture simple de la page : une requête, un User-Agent de navigateur.

    Aucun contournement de protection anti-robot (pas de proxy, pas de rotation,
    pas de navigateur automatisé). Statut ≠ 200, erreur réseau ou texte de moins
    de 200 caractères → ImportManuelErreur(MESSAGE_PAGE_ILLISIBLE).
    """
    try:
        resp = requests.get(url, headers=HEADERS_PAGE, timeout=TIMEOUT_PAGE)
    except requests.RequestException as e:
        logger.info("[MANUEL] Lecture de %s impossible : %s", url, e)
        raise ImportManuelErreur(MESSAGE_PAGE_ILLISIBLE) from e
    if resp.status_code != 200:
        logger.info("[MANUEL] Lecture de %s : HTTP %d", url, resp.status_code)
        raise ImportManuelErreur(MESSAGE_PAGE_ILLISIBLE)

    soup = BeautifulSoup(resp.text, "lxml")
    for balise in soup(["script", "style", "noscript", "svg", "template"]):
        balise.decompose()
    lignes = (re.sub(r"\s+", " ", l).strip() for l in soup.get_text(separator="\n").splitlines())
    texte = "\n".join(l for l in lignes if l)
    if len(texte) < LONGUEUR_MIN_PAGE:
        logger.info("[MANUEL] Lecture de %s : %d caractères seulement", url, len(texte))
        raise ImportManuelErreur(MESSAGE_PAGE_ILLISIBLE)
    return texte


# ── 2. Structuration Haiku ───────────────────────────────────────────────────

def _client_anthropic():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("[MANUEL] ANTHROPIC_API_KEY non définie : structuration impossible")
        return None
    from anthropic import Anthropic
    return Anthropic(api_key=api_key)


def _entier_ou_none(valeur) -> int | None:
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        return int(round(float(str(valeur).replace(" ", "").replace(",", "."))))
    except (TypeError, ValueError):
        return None


def _texte_ou_none(valeur) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def structurer_avec_haiku(texte: str, client=None) -> dict | None:
    """Un appel Haiku → champs structurés, ou None si l'appel ou le JSON échoue."""
    from src.filters.ai_filter import MODELE   # même modèle que le filtre IA

    client = client if client is not None else _client_anthropic()
    if client is None:
        return None
    contenu = ""
    try:
        reponse = client.messages.create(
            model=MODELE,
            max_tokens=4096,
            # Le SDK installé refuse temperature : même contournement que ai_filter
            extra_body={"temperature": 0},
            messages=[{"role": "user", "content": PROMPT_STRUCTURATION + texte[:MAX_TEXTE_HAIKU]}],
        )
        contenu = reponse.content[0].text.strip()
        contenu = contenu.replace("```json", "").replace("```", "").strip()
        data = json.loads(contenu)
        if not isinstance(data, dict):
            raise ValueError("la réponse n'est pas un objet JSON")
    except Exception as e:
        logger.error("[MANUEL] Structuration Haiku en échec : %s — réponse : %r", e, contenu[:300])
        return None

    type_contrat = _texte_ou_none(data.get("type_contrat"))
    if type_contrat not in TYPES_CONTRAT:
        type_contrat = None
    tjm_min, tjm_max = _entier_ou_none(data.get("tjm_min")), _entier_ou_none(data.get("tjm_max"))
    if tjm_min is not None and tjm_max is None:
        tjm_max = tjm_min
    if tjm_max is not None and tjm_min is None:
        tjm_min = tjm_max
    return {
        "titre": _texte_ou_none(data.get("titre")),
        "entreprise": _texte_ou_none(data.get("entreprise")),
        "lieu": _texte_ou_none(data.get("lieu")),
        "type_contrat": type_contrat,
        "tjm_min": tjm_min,
        "tjm_max": tjm_max,
        "description": _texte_ou_none(data.get("description")),
    }


# ── 3. Enregistrement ────────────────────────────────────────────────────────

def enregistrer(champs: dict, url: str | None) -> tuple[int, bool]:
    """INSERT d'une offre "Manuelle", ou UPDATE si le hash existe déjà.

    Colonnes renseignées comme par les collecteurs (sauvegarder()) : hash,
    titre, entreprise, lieu, type_contrat, source, url, description, tjm_min,
    tjm_max, date_collecte, date_derniere_vue. Les colonnes du pipeline
    (resume_ia, score_ia, type_contrat_clarifie, envoyee…) restent à leur
    valeur par défaut. En cas de mise à jour, date_collecte (première fois vue),
    scores IA et actions d'Alice sont conservés.

    Retourne (offre_id, deja_presente).
    """
    database.initialiser()   # tables + migrations, idempotent
    hash_offre = database.get_hash(champs["titre"], champs.get("entreprise") or "", SOURCE_MANUELLE)
    maintenant = datetime.now().isoformat()

    with database._connexion() as conn:
        existante = conn.execute("SELECT id FROM offres WHERE hash = ?", (hash_offre,)).fetchone()
        if existante:
            conn.execute(
                """
                UPDATE offres SET
                    titre = ?, entreprise = ?, lieu = ?, type_contrat = ?,
                    url = COALESCE(?, url), description = ?,
                    tjm_min = ?, tjm_max = ?, date_derniere_vue = ?
                WHERE id = ?
                """,
                (
                    champs["titre"], champs.get("entreprise"), champs.get("lieu"),
                    champs.get("type_contrat"), url, champs.get("description"),
                    champs.get("tjm_min"), champs.get("tjm_max"), maintenant,
                    existante["id"],
                ),
            )
            return existante["id"], True

        cur = conn.execute(
            """
            INSERT INTO offres
              (hash, titre, entreprise, lieu, type_contrat, source, url, description,
               tjm_min, tjm_max, date_collecte, date_derniere_vue)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hash_offre, champs["titre"], champs.get("entreprise"), champs.get("lieu"),
                champs.get("type_contrat"), SOURCE_MANUELLE, url, champs.get("description"),
                champs.get("tjm_min"), champs.get("tjm_max"), maintenant, maintenant,
            ),
        )
        return cur.lastrowid, False


# ── 4. Matching immédiat ─────────────────────────────────────────────────────

def calculer_matchings_offre(offre_id: int) -> int:
    """Matching de CETTE offre contre tous les CVs profilés.

    Réutilise calculer_score_global (src/matching/scoring.py) et la même
    écriture que src/matching/calculer.py. Retourne le nombre de matchings.
    """
    from src.matching.scoring import calculer_score_global

    with database._connexion() as conn:
        offre_row = conn.execute("SELECT * FROM offres WHERE id = ?", (offre_id,)).fetchone()
        if offre_row is None:
            return 0
        offre = dict(offre_row)
        cvs = conn.execute(
            "SELECT * FROM cvs WHERE competences_techniques IS NOT NULL"
        ).fetchall()
        for cv_row in cvs:
            scores = calculer_score_global(dict(cv_row), offre)
            conn.execute(
                """
                INSERT INTO matchings (
                    cv_id, offre_id,
                    score_global, score_competences, score_domaine,
                    score_experience, score_contrat, score_lieu,
                    details_json, date_calcul
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                -- UPSERT et non INSERT OR REPLACE : REPLACE supprime la ligne avant
                -- de la réinsérer, ce qui remettait ajout_manuel à 0 à chaque
                -- recalcul. Ici seuls les scores sont réécrits.
                ON CONFLICT(cv_id, offre_id) DO UPDATE SET
                    score_global      = excluded.score_global,
                    score_competences = excluded.score_competences,
                    score_domaine     = excluded.score_domaine,
                    score_experience  = excluded.score_experience,
                    score_contrat     = excluded.score_contrat,
                    score_lieu        = excluded.score_lieu,
                    details_json      = excluded.details_json,
                    date_calcul       = excluded.date_calcul
                """,
                (
                    cv_row["id"], offre_id,
                    scores["score_global"], scores["score_competences"], scores["score_domaine"],
                    scores["score_experience"], scores["score_contrat"], scores["score_lieu"],
                    scores["details_json"],
                ),
            )
        return len(cvs)


# ── Point d'entrée ───────────────────────────────────────────────────────────

def importer_offre_manuelle(url: str | None, texte: str | None, client=None) -> dict:
    """Import complet. Lève ImportManuelErreur (→ 422) si la saisie est inexploitable."""
    url = (url or "").strip() or None
    texte = (texte or "").strip() or None

    if not url and not texte:
        raise ImportManuelErreur(MESSAGE_SAISIE_VIDE)
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        raise ImportManuelErreur(MESSAGE_URL_INVALIDE)
    if not texte:
        texte = recuperer_texte_page(url)

    champs = structurer_avec_haiku(texte, client=client)
    structuration_reussie = champs is not None and bool(champs.get("titre"))
    if champs is None:
        champs = {"entreprise": None, "lieu": None, "type_contrat": None,
                  "tjm_min": None, "tjm_max": None}
    if not structuration_reussie:
        # Secours : 120 premiers caractères du texte, sauts de ligne et espaces normalisés
        champs["titre"] = champs.get("titre") or re.sub(r"\s+", " ", texte).strip()[:LONGUEUR_TITRE_SECOURS]
        champs["description"] = texte
    champs["description"] = champs.get("description") or texte

    offre_id, deja_presente = enregistrer(champs, url)

    try:
        nb_matchings = calculer_matchings_offre(offre_id)
    except Exception as e:   # pas de table cvs / matchings : l'offre reste enregistrée
        logger.warning("[MANUEL] Matching de l'offre %d impossible : %s", offre_id, e)
        nb_matchings = 0

    logger.info(
        "[MANUEL] Offre %d %s (structuration %s, %d matching(s)) : %s",
        offre_id, "mise à jour" if deja_presente else "créée",
        "réussie" if structuration_reussie else "en échec", nb_matchings, champs["titre"][:80],
    )
    return {
        "id": offre_id,
        "titre": champs["titre"],
        "entreprise": champs.get("entreprise"),
        "lieu": champs.get("lieu"),
        "type_contrat": champs.get("type_contrat"),
        "tjm_min": champs.get("tjm_min"),
        "tjm_max": champs.get("tjm_max"),
        "description": champs["description"],
        "url": url,
        "deja_presente": deja_presente,
        "structuration_reussie": structuration_reussie,
        "nb_matchings": nb_matchings,
    }
