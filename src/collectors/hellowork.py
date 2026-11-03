"""
Collecteur HelloWork (hellowork.com).

Scraping HTML statique via requests + BeautifulSoup.
Pages de résultats publiques, pas de login requis.
Cible : chef de projet / business analyst / MOA / PMO / test manager
        missions Indépendant + Freelance, secteurs banque-assurance-finance,
        informatique-SSII et services aux entreprises
        Île-de-France + télétravail complet (national)

5 pages max par URL, délai entre requêtes : delai_secondes (config).
La carte de résultat ne contient pas de description : chaque offre unique
est enrichie depuis sa page détail (plafond MAX_ENRICHISSEMENT).
"""

import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..utils.parsing import parse_salaire, parse_tjm
from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hellowork.com"
URL_RECHERCHE = f"{BASE_URL}/fr-fr/emploi/recherche.html"
SOURCE_HW = "HelloWork"
PAGES_MAX = 5
MAX_ENRICHISSEMENT = 250   # pages détail visitées au maximum par collecte
DELAI_DETAIL = 1           # secondes entre deux pages détail

MOTS_CLES = ["chef de projet", "business analyst", "MOA", "PMO", "test manager"]

# Paramètres communs à toutes les recherches (relevés sur le site).
# Liste de tuples : les paramètres c et s sont répétés.
PARAMS_COMMUNS = [
    ("k_autocomplete", ""),
    ("st", "relevance"),
    ("c", "Independant"),
    ("c", "Freelance"),
    ("cod", "all"),
    ("msa", "0"),
    ("d", "all"),
    ("s", "Banq_assur_finan"),
    ("s", "Inform_SSII"),
    ("s", "Serv_entreprise"),
]

# (paramètres propres au lieu, suffixe du libellé)
LIEUX = [
    (
        [
            ("l", "Île-de-France"),
            ("l_autocomplete", "http://www.rj.com/commun/localite/region/11"),
            ("ray", "20"),
        ],
        "IDF",
    ),
    # Télétravail complet, sans lieu : recherche nationale (combinaison déduite,
    # à vérifier au premier run réel).
    ([("t", "Complet")], "remote"),
]


def _url_recherche(mot_cle: str, params_lieu: list) -> str:
    params = [("k", mot_cle)] + PARAMS_COMMUNS + params_lieu
    return URL_RECHERCHE + "?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in params)


# (url_base, label pour les logs) — page 1 sans paramètre p
URLS_RECHERCHE = [
    (_url_recherche(mot, params_lieu), f"{mot} {suffixe}")
    for params_lieu, suffixe in LIEUX
    for mot in MOTS_CLES
]

HEADERS_HW = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Clés normalisées (minuscules, sans accents) → libellé standard
CONTRATS_HW = {
    "freelance": "Freelance",
    "independant": "Freelance",
    "cdi": "CDI",
    "cdd": "CDD",
    "stage": "Stage",
    "alternance": "Alternance",
}

# Filet de sécurité : aria-label du lien titre, de la forme
# "Voir offre de {titre} à {lieu}, chez {entreprise}, pour un {contrat},
#  avec un salaire de {salaire}, en temps plein"
_RE_ARIA = re.compile(
    r"^Voir offre de (?P<titre>.+?) à (?P<lieu>.+?), chez (?P<entreprise>.+?)"
    r"(?:, pour un (?P<contrat>.+?))?"
    r"(?:, avec un salaire de (?P<salaire>.+?))?"
    r"(?:, en [^,]+)?$"
)

_RE_DATE_RELATIVE = re.compile(r"il y a\s+(\d+)\s+(minute|heure|jour|semaine|mois)", re.IGNORECASE)


def _texte(el) -> str:
    """Texte d'un élément avec espaces entre les nœuds enfants, espaces normalisés.

    Avec séparateur : get_text(strip=True) seul colle les nœuds texte adjacents.
    """
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True)).strip()


def _sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte.strip().lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def _normaliser_contrat(texte: str) -> str:
    """"Indépendant" → "Freelance", "CDI" → "CDI"… ; inconnu : texte tel quel."""
    if not texte:
        return ""
    return CONTRATS_HW.get(_sans_accents(texte), texte)


def _montants(texte: str) -> tuple[int | None, int | None, int | None, int | None]:
    """'500 - 650 € / jour' → (500, 650, None, None) ; salaire annuel → (None, None, min, max)."""
    texte = (texte or "").replace("⁄", "/").replace("\xa0", " ").replace(" ", " ")
    tjm_min, tjm_max = parse_tjm(texte)
    if tjm_min is not None:
        return tjm_min, tjm_max, None, None
    sal_min, sal_max = parse_salaire(texte)
    return None, None, sal_min, sal_max


def _date_relative(texte: str) -> datetime | None:
    """'il y a 1 jour' → maintenant - 1 jour ; format non reconnu → None."""
    m = _RE_DATE_RELATIVE.search(texte or "")
    if not m:
        return None
    n, unite = int(m.group(1)), m.group(2).lower()
    delta = {
        "minute": timedelta(minutes=n),
        "heure": timedelta(hours=n),
        "jour": timedelta(days=n),
        "semaine": timedelta(weeks=n),
        "mois": timedelta(days=30 * n),
    }[unite]
    return datetime.now() - delta


class HelloWorkCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        self.erreurs_collecte = []
        self.nb_recherches = len(URLS_RECHERCHE)
        toutes = []
        for url_base, label in URLS_RECHERCHE:
            toutes.extend(self._scraper_url(url_base, label))

        # Dédup AVANT l'enrichissement : une page détail n'est visitée qu'une fois
        uniques = self._dedupliquer(toutes)
        self._enrichir_descriptions(uniques)
        logger.info("[HelloWork] Total : %d offres uniques collectées", len(uniques))
        return uniques

    # ── Pagination ────────────────────────────────────────────────────────────

    def _scraper_url(self, url_base: str, label: str) -> list[dict]:
        offres = []
        for page_num in range(1, PAGES_MAX + 1):
            url = url_base if page_num == 1 else f"{url_base}&p={page_num}"

            try:
                time.sleep(self.delai)
                resp = self.session.get(url, headers=HEADERS_HW, timeout=15)

                if resp.status_code == 404:
                    logger.info("[HelloWork] '%s' page %d : fin de pagination (404)", label, page_num)
                    break
                if resp.status_code != 200:
                    logger.warning("[HelloWork] '%s' page %d : HTTP %d", label, page_num, resp.status_code)
                    self.erreurs_collecte.append(f"'{label}' page {page_num} : HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                cartes = soup.select('div[data-cy="serpCard"]')

                if not cartes:
                    logger.info("[HelloWork] '%s' page %d : 0 carte — fin de pagination", label, page_num)
                    break

                nouvelles = [o for o in (self._parser_carte(c) for c in cartes) if o]
                logger.info("[HelloWork] Page %d de '%s' : %d offres extraites", page_num, label, len(nouvelles))
                offres.extend(nouvelles)

            except Exception as e:
                logger.error("[HelloWork] Erreur '%s' page %d : %s", label, page_num, e)
                self.erreurs_collecte.append(
                    f"'{label}' page {page_num} : {type(e).__name__} — {str(e)[:80]}"
                )
                break

        return offres

    # ── Parsing d'une carte ───────────────────────────────────────────────────

    def _parser_carte(self, carte) -> dict | None:
        try:
            # ── URL + source_id — OBLIGATOIRES ────────────────────────────────────
            lien = carte.select_one('a[data-cy="offerTitle"]')
            href = lien.get("href", "") if lien else ""
            if not href:
                return None
            url = href if href.startswith("http") else BASE_URL + href
            m_id = re.search(r"(\d+)\.html", href)
            source_id = m_id.group(1) if m_id else ""

            # ── Titre / entreprise : spans du <h3> ───────────────────────────────
            h3 = carte.find("h3")
            titre = _texte(h3.find("span", class_="block")) if h3 else ""
            entreprise = _texte(h3.find("span", class_="inline")) if h3 else ""

            # ── Lieu, contrat ────────────────────────────────────────────────────
            lieu = _texte(carte.select_one('div[data-cy="localisationCard"]'))
            contrat_brut = _texte(carte.select_one('div[data-cy="contractCard"]'))

            # ── TJM / salaire : premier tag contenant un montant en € ───────────
            texte_montant = ""
            for tag in carte.select("div.tag-secondary-s.typo-s-bold"):
                t = _texte(tag)
                if "€" in t:
                    texte_montant = t
                    break

            # ── Date relative ("il y a 1 jour") ──────────────────────────────────
            date_pub = None
            for div in carte.select("div.typo-s.text-grey-500"):
                date_pub = _date_relative(_texte(div))
                if date_pub:
                    break

            # ── Secours : aria-label du lien si un champ est vide ────────────────
            aria = (lien.get("aria-label") or "").strip() if lien else ""
            if aria and not (titre and entreprise and lieu and contrat_brut and texte_montant):
                m = _RE_ARIA.match(re.sub(r"\s+", " ", aria))
                if m:
                    titre = titre or (m.group("titre") or "").strip()
                    lieu = lieu or (m.group("lieu") or "").strip()
                    entreprise = entreprise or (m.group("entreprise") or "").strip()
                    contrat_brut = contrat_brut or (m.group("contrat") or "").strip()
                    texte_montant = texte_montant or (m.group("salaire") or "").strip()

            if not titre:
                return None

            tjm_min, tjm_max, salaire_min, salaire_max = _montants(texte_montant)

            offre = self.normaliser(
                titre=titre,
                entreprise=entreprise,
                lieu=lieu,
                type_contrat=_normaliser_contrat(contrat_brut),
                url=url,
                description="",   # rempli depuis la page détail
                source=SOURCE_HW,
            )
            offre["source_id"] = source_id
            offre["tjm_min"] = tjm_min
            offre["tjm_max"] = tjm_max
            offre["salaire_min"] = salaire_min
            offre["salaire_max"] = salaire_max
            if date_pub:
                offre["date_publication"] = date_pub.isoformat()

            return offre

        except Exception as e:
            logger.debug("[HelloWork] Erreur parsing carte : %s", e)
            return None

    # ── Enrichissement des descriptions (pages détail) ────────────────────────

    def _enrichir_descriptions(self, offres: list) -> None:
        if len(offres) > MAX_ENRICHISSEMENT:
            logger.warning(
                "[HelloWork] %d offres uniques : seules les %d premières sont enrichies "
                "(les autres gardent une description vide)",
                len(offres), MAX_ENRICHISSEMENT,
            )
        echecs = 0
        for offre in offres[:MAX_ENRICHISSEMENT]:
            offre["description"] = self._description_detail(offre["url"])
            if not offre["description"]:
                echecs += 1
        if echecs:
            logger.warning("[HelloWork] %d page(s) détail sans description (échec ou sélecteur absent)", echecs)

    def _description_detail(self, url: str) -> str:
        """Description depuis la page détail ; "" si échec ou sélecteur introuvable."""
        try:
            time.sleep(DELAI_DETAIL)
            resp = self.session.get(url, headers=HEADERS_HW, timeout=15)
            if resp.status_code != 200:
                logger.debug("[HelloWork] Page détail HTTP %d : %s", resp.status_code, url)
                return ""
            soup = BeautifulSoup(resp.text, "lxml")
            bloc = soup.select_one('div[data-truncate-text-target="content"]')
            return _texte(bloc)[:3000]
        except Exception as e:
            logger.debug("[HelloWork] Page détail en échec (%s) : %s", url, e)
            return ""

    # ── Déduplication par URL (même offre dans plusieurs recherches) ─────────
    @staticmethod
    def _dedupliquer(offres: list) -> list:
        vus = set()
        uniques = []
        for o in offres:
            cle = o.get("url", "") or o["titre"].lower().strip()
            if cle not in vus:
                vus.add(cle)
                uniques.append(o)
        return uniques
