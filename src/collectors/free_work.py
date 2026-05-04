"""
Collecteur Free-Work (free-work.com).

Scraping HTML statique via requests + BeautifulSoup.
Pages de résultats publiques, pas de login requis.
Cible : chef de projet / business analyst / MOA
        Île-de-France + full remote

5 pages max par URL, délai 2s entre requêtes.
"""

import logging
import time
from datetime import datetime

from bs4 import BeautifulSoup

from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.free-work.com"
PAGES_MAX = 5

# (url_base, label pour les logs)
URLS_RECHERCHE = [
    (
        "https://www.free-work.com/fr/tech-it/jobs?locations=fr~ile-de-france~~&query=chef%20de%20projet",
        "chef de projet IDF",
    ),
    (
        "https://www.free-work.com/fr/tech-it/jobs?locations=fr~ile-de-france~~&query=business%20analyst",
        "business analyst IDF",
    ),
    (
        "https://www.free-work.com/fr/tech-it/jobs?locations=fr~ile-de-france~~&query=MOA",
        "MOA IDF",
    ),
    (
        "https://www.free-work.com/fr/tech-it/jobs?query=chef%20de%20projet&remote=full",
        "chef de projet remote",
    ),
    (
        "https://www.free-work.com/fr/tech-it/jobs?query=business%20analyst&remote=full",
        "business analyst remote",
    ),
    (
        "https://www.free-work.com/fr/tech-it/jobs?query=MOA&remote=full",
        "MOA remote",
    ),
]

HEADERS_FW = {
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

CONTRATS_FW = {
    "mission freelance": "Freelance",
    "freelance": "Freelance",
    "cdi": "CDI",
    "cdd": "CDD",
    "interim": "Intérim",
    "intérim": "Intérim",
}


class FreeWorkCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        toutes = []
        for url_base, label in URLS_RECHERCHE:
            toutes.extend(self._scraper_url(url_base, label))

        uniques = self._dedupliquer(toutes)
        logger.info("[Free-Work] Total : %d offres uniques collectées", len(uniques))
        return uniques

    # ── Pagination ────────────────────────────────────────────────────────────

    def _scraper_url(self, url_base: str, label: str) -> list[dict]:
        offres = []
        _diag_fait = False  # TEMPORAIRE — diagnostic sélecteurs (1ère page, 1ère URL)

        for page_num in range(1, PAGES_MAX + 1):
            url = url_base if page_num == 1 else f"{url_base}&page={page_num}"

            try:
                time.sleep(self.delai)
                resp = self.session.get(url, headers=HEADERS_FW, timeout=15)

                if resp.status_code == 404:
                    logger.info("[Free-Work] '%s' page %d : fin de pagination (404)", label, page_num)
                    break
                if resp.status_code != 200:
                    logger.warning("[Free-Work] '%s' page %d : HTTP %d", label, page_num, resp.status_code)
                    break

                soup = BeautifulSoup(resp.text, "lxml")

                # TEMPORAIRE — diagnostic sélecteurs (1ère page de la 1ère URL uniquement)
                if page_num == 1 and not _diag_fait:
                    _diag_fait = True
                    tous_a = soup.find_all("a", href=True)
                    a_techit = [a for a in tous_a if "/fr/tech-it/" in (a.get("href") or "")]
                    a_job = [a for a in tous_a if "/job-" in (a.get("href") or "")]
                    a_les_deux = [a for a in tous_a if "/fr/tech-it/" in (a.get("href") or "") and "/job-" in (a.get("href") or "")]
                    logger.info("[FW-DIAG] HTML : %d caractères", len(resp.text))
                    logger.info("[FW-DIAG] Total <a> : %d", len(tous_a))
                    logger.info("[FW-DIAG] <a> avec /fr/tech-it/ : %d", len(a_techit))
                    logger.info("[FW-DIAG] <a> avec /job- : %d", len(a_job))
                    logger.info("[FW-DIAG] <a> avec les deux : %d", len(a_les_deux))
                    echantillon = [a.get("href", "") for a in tous_a[:10]]
                    logger.info("[FW-DIAG] Échantillon de 10 hrefs :")
                    for i, href in enumerate(echantillon, 1):
                        logger.info("[FW-DIAG]   %d) %s", i, href)
                # FIN TEMPORAIRE

                cartes = soup.find_all(
                    "a", href=lambda h: h and "/fr/tech-it/" in h and "/job-" in h
                )

                if not cartes:
                    logger.info("[Free-Work] '%s' page %d : 0 carte — fin de pagination", label, page_num)
                    break

                nouvelles = []
                for idx, carte in enumerate(cartes):
                    # TEMPORAIRE — debug parsing des 3 premières cartes, 1ère page seulement
                    debug = (page_num == 1 and idx < 3 and label == URLS_RECHERCHE[0][1])
                    offre = self._parser_carte(carte, debug=debug)
                    if offre:
                        nouvelles.append(offre)
                logger.info("[Free-Work] Page %d de '%s' : %d offres extraites", page_num, label, len(nouvelles))
                offres.extend(nouvelles)

            except Exception as e:
                logger.error("[Free-Work] Erreur '%s' page %d : %s", label, page_num, e)
                break

        return offres

    # ── Parsing d'une carte ───────────────────────────────────────────────────

    def _parser_carte(self, carte, debug: bool = False) -> dict | None:  # TEMPORAIRE: debug param
        try:
            # ── URL + source_id — OBLIGATOIRES ───────────────────────────────────
            href = carte.get("href", "")
            if not href:
                if debug:
                    logger.info("[FW-CARD-DEBUG] REJET : href vide")
                return None
            url = BASE_URL + href
            source_id = href.rstrip("/").split("/")[-1]
            if debug:
                logger.info("[FW-CARD-DEBUG] url : '%s'", url)

            # ── Titre — OBLIGATOIRE ───────────────────────────────────────────────
            h3 = carte.find("h3")
            if not h3:
                if debug:
                    logger.info("[FW-CARD-DEBUG] REJET : pas de <h3> | HTML : %s", str(carte)[:500])
                return None
            titre_span = h3.find("span", class_="fw-text-highlight")
            titre = titre_span.get_text(strip=True) if titre_span else h3.get_text(strip=True)
            if debug:
                logger.info("[FW-CARD-DEBUG] titre extrait : '%s'", titre)
            if not titre:
                if debug:
                    logger.info("[FW-CARD-DEBUG] REJET : titre vide | HTML h3 : %s", str(h3)[:500])
                return None

            # ── Type de contrat ───────────────────────────────────────────────────
            type_contrat = "Freelance"
            for span in carte.find_all("span"):
                texte_span = span.get_text(strip=True).lower()
                if texte_span in CONTRATS_FW:
                    type_contrat = CONTRATS_FW[texte_span]
                    break
            if debug:
                logger.info("[FW-CARD-DEBUG] type_contrat : '%s'", type_contrat)

            # ── Entreprise ────────────────────────────────────────────────────────
            entreprise = ""
            div_ent = carte.find(
                "div", class_=lambda c: c and "font-medium" in c and "truncate" in c
            )
            if div_ent:
                entreprise = div_ent.get_text(strip=True)
            if debug:
                logger.info("[FW-CARD-DEBUG] entreprise : '%s'", entreprise)

            # ── Localisation ──────────────────────────────────────────────────────
            lieu = ""
            span_title = carte.find("span", title=True)
            if span_title:
                lieu = span_title["title"]
            if debug:
                logger.info("[FW-CARD-DEBUG] lieu : '%s'", lieu)

            # ── Date de publication ───────────────────────────────────────────────
            date_pub = None
            time_tag = carte.find("time")
            date_str = time_tag.get_text(strip=True) if time_tag else ""
            if debug:
                logger.info("[FW-CARD-DEBUG] date_str : '%s'", date_str)
            if date_str:
                try:
                    date_pub = datetime.strptime(date_str, "%d/%m/%Y")
                except ValueError:
                    pass

            # ── Description (résumé) + tags compétences ───────────────────────────
            description = ""
            div_desc = carte.find(
                "div", class_=lambda c: c and "fw-text-highlight" in c and "line-clamp-3" in c
            )
            if div_desc:
                description = div_desc.get_text(strip=True)

            tags = [
                s.get_text(strip=True)
                for s in carte.find_all("span", class_=lambda c: c and "bg-brand-75" in c)
                if s.get_text(strip=True)
            ]
            if tags:
                suffix = f"Compétences : {', '.join(tags)}"
                description = f"{description} | {suffix}" if description else suffix
            if debug:
                logger.info("[FW-CARD-DEBUG] description (50 premiers chars) : '%s'", description[:50])

            # ── Construction de l'offre ───────────────────────────────────────────
            offre = self.normaliser(
                titre=titre,
                entreprise=entreprise,
                lieu=lieu,
                type_contrat=type_contrat,
                url=url,
                description=description[:1500],
                source=self.nom,
            )
            offre["source_id"] = source_id
            offre["tjm_min"] = None
            offre["tjm_max"] = None
            if date_pub:
                offre["date_publication"] = date_pub.isoformat()

            return offre

        except Exception as e:
            logger.error("[FW-CARD-DEBUG] EXCEPTION carte : %s", e, exc_info=True)  # TEMPORAIRE
            logger.info("[FW-CARD-DEBUG] HTML brut de la carte :\n%s", str(carte)[:1000])  # TEMPORAIRE
            return None

    # ── Déduplication par URL (même offre peut apparaître dans plusieurs recherches)
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
