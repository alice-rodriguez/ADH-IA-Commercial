"""
Collecteur Welcome to the Jungle (WTJ).

Scraping HTML statique via requests + BeautifulSoup.
Pages emploi publiques ciblées :
  /fr/pages/emploi-chef-de-projet
  /fr/pages/emploi-business-analyst
  /fr/pages/emploi-consultant-moa

5 pages de pagination max par URL (20 offres/page → ~300 offres brutes).
Aucun filtre côté collecteur — le tri Île-de-France / banque / CDI
est délégué au pré-filtre Python en aval.
"""

import logging
import time

from bs4 import BeautifulSoup

from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.welcometothejungle.com"
PAGES_MAX = 5

URLS_EMPLOI = [
    "/fr/pages/emploi-chef-de-projet",
    "/fr/pages/emploi-business-analyst",
    "/fr/pages/emploi-consultant-moa",
]

HEADERS_WTJ = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class WTJCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        toutes = []
        for chemin in URLS_EMPLOI:
            toutes.extend(self._scraper_chemin(chemin))

        uniques = self._dedupliquer(toutes)
        logger.info("[WTJ] Total : %d offres uniques collectées", len(uniques))
        return uniques

    # ── Pagination ────────────────────────────────────────────────────────────

    def _scraper_chemin(self, chemin: str) -> list[dict]:
        offres = []
        for page_num in range(1, PAGES_MAX + 1):
            url = BASE_URL + chemin
            if page_num > 1:
                url += f"?page={page_num}"

            try:
                time.sleep(self.delai)
                resp = self.session.get(url, headers=HEADERS_WTJ, timeout=15)

                if resp.status_code == 404:
                    logger.info("[WTJ] '%s' page %d : fin de pagination (404)", chemin, page_num)
                    break
                if resp.status_code != 200:
                    logger.warning("[WTJ] '%s' page %d : HTTP %d", chemin, page_num, resp.status_code)
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                cartes = soup.find_all(
                    "li", attrs={"data-testid": "jobs-results-list-list-item-wrapper"}
                )
                if not cartes:
                    logger.info("[WTJ] '%s' page %d : 0 carte — fin de pagination", chemin, page_num)
                    break

                nouvelles = [o for o in (self._parser_carte(c) for c in cartes) if o]
                logger.info("[WTJ] Page %d de '%s' : %d offres extraites", page_num, chemin, len(nouvelles))
                offres.extend(nouvelles)

            except Exception as e:
                logger.error("[WTJ] Erreur '%s' page %d : %s", chemin, page_num, e)
                break

        return offres

    # ── Parsing d'une carte ───────────────────────────────────────────────────

    def _parser_carte(self, carte) -> dict | None:
        # Titre — OBLIGATOIRE (h2 stable, présent dans toutes les cartes)
        h2 = carte.find("h2")
        titre = h2.get_text(strip=True) if h2 else ""
        if not titre:
            return None

        # URL — OBLIGATOIRE (premier lien href contenant "/jobs/")
        lien = carte.find("a", href=lambda h: h and "/jobs/" in h)
        if not lien:
            return None
        url = BASE_URL + lien["href"]

        # Entreprise — best effort
        # Le logo de l'entreprise est un <img> dont le alt contient le nom
        entreprise = ""
        img = carte.find("img")
        if img and img.get("alt", "").strip():
            entreprise = img["alt"].strip()

        # Description courte — best effort
        p = carte.find("p")
        description = p.get_text(strip=True) if p else ""

        # Type de contrat — best effort
        # WTJ utilise une icône SVG avec alt="Contract" suivie du texte
        type_contrat = self._texte_icone(carte, "Contract") or "CDI/CDD"

        # Localisation — best effort
        # WTJ utilise une icône SVG avec alt="Location" suivie de la ville
        lieu = self._texte_icone(carte, "Location") or ""

        return self.normaliser(
            titre=titre,
            entreprise=entreprise,
            lieu=lieu,
            type_contrat=type_contrat,
            url=url,
            description=description[:1500],
            source=self.nom,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _texte_icone(carte, alt_value: str) -> str:
        """
        Extrait le texte associé à une icône WTJ.
        WTJ identifie ses icônes SVG/IMG via l'attribut alt ou aria-label.
        On remonte au conteneur parent pour récupérer le texte adjacent.
        """
        icone = carte.find(
            lambda tag: tag.name in ("svg", "img")
            and (
                tag.get("alt") == alt_value
                or tag.get("aria-label") == alt_value
            )
        )
        if not icone:
            return ""
        conteneur = icone.parent
        return conteneur.get_text(separator=" ", strip=True) if conteneur else ""

    @staticmethod
    def _dedupliquer(offres: list) -> list:
        vus = set()
        uniques = []
        for o in offres:
            cle = (o["titre"].lower().strip(), o.get("entreprise", "").lower().strip())
            if cle not in vus:
                vus.add(cle)
                uniques.append(o)
        return uniques
