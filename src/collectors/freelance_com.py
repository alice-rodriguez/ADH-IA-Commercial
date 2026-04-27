"""
Collecteur Freelance.com — missions freelance IT et conseil.
"""

import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import BaseCollector

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.freelance.com/missions.php"


class FreelanceComCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        offres = []
        requetes = self._construire_requetes(criteres)

        for requete in requetes:
            try:
                nouvelles = self._scraper_page(requete)
                offres.extend(nouvelles)
                logger.info("[Freelance.com] '%s' → %d offres", requete, len(nouvelles))
            except Exception as e:
                logger.error("[Freelance.com] Erreur pour '%s' : %s", requete, e)

        offres = self._dedupliquer(offres)
        logger.info("[Freelance.com] Total : %d offres uniques", len(offres))
        return offres

    def _construire_requetes(self, criteres: dict) -> list:
        profils = criteres.get("profils", [])
        return [p for p in profils[:3]]

    def _scraper_page(self, requete: str) -> list:
        params = {
            "filter[keywords]": requete,
            "filter[localisation]": "Paris",
            "filter[tjm_max]": "",
        }
        url = f"{SEARCH_URL}?{urlencode(params)}"

        try:
            response = self._get(url)
        except Exception:
            return []

        if not response:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        offres = []

        cartes = (
            soup.select("div.mission-item, article.mission, div.result-item")
            or soup.select("li.mission")
        )

        for carte in cartes[:20]:
            try:
                titre_el = carte.select_one("h2, h3, .title, .mission-title, a.mission-link")
                titre = titre_el.get_text(strip=True) if titre_el else ""

                entreprise_el = carte.select_one(".client, .company, .entreprise")
                entreprise = entreprise_el.get_text(strip=True) if entreprise_el else "Client confidentiel"

                lieu_el = carte.select_one(".location, .lieu, .city")
                lieu = lieu_el.get_text(strip=True) if lieu_el else "Paris"

                lien_el = carte.select_one("a[href*='mission'], h2 a, h3 a")
                href = lien_el["href"] if lien_el else ""
                lien = href if href.startswith("http") else f"https://www.freelance.com{href}"

                description_el = carte.select_one(".description, .excerpt, p")
                description = description_el.get_text(strip=True) if description_el else titre

                tjm_el = carte.select_one(".tjm, .rate, .daily-rate")
                tjm = tjm_el.get_text(strip=True) if tjm_el else ""
                if tjm:
                    description = f"TJM : {tjm}. {description}"

                if not titre:
                    continue

                offres.append(
                    self.normaliser(
                        titre=titre,
                        entreprise=entreprise,
                        lieu=lieu,
                        type_contrat="Freelance",
                        url=lien,
                        description=description,
                        source=self.nom,
                    )
                )
            except Exception as e:
                logger.debug("[Freelance.com] Erreur parsing : %s", e)

        return offres

    @staticmethod
    def _dedupliquer(offres: list) -> list:
        vus = set()
        uniques = []
        for o in offres:
            cle = (o["titre"].lower(), o["entreprise"].lower())
            if cle not in vus:
                vus.add(cle)
                uniques.append(o)
        return uniques
