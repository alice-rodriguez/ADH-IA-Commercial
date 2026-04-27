"""
Collecteur Indeed France.

Note : Indeed peut bloquer le scraping selon les périodes.
Si cette source retourne 0 offre plusieurs jours de suite,
désactivez-la dans config/sources.yaml (active: false).
Délai de 5s entre requêtes pour limiter les blocages.
"""

import logging
from urllib.parse import urlencode, quote_plus

from bs4 import BeautifulSoup

from .base import BaseCollector

logger = logging.getLogger(__name__)

SEARCH_URL = "https://fr.indeed.com/emplois"


class IndeedCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        offres = []
        requetes = self._construire_requetes(criteres)

        for requete, lieu in requetes:
            try:
                nouvelles = self._scraper_page(requete, lieu)
                offres.extend(nouvelles)
                logger.info("[Indeed] '%s' à '%s' → %d offres", requete, lieu, len(nouvelles))
            except Exception as e:
                logger.error("[Indeed] Erreur pour '%s' : %s", requete, e)

        offres = self._dedupliquer(offres)
        logger.info("[Indeed] Total : %d offres uniques", len(offres))
        return offres

    def _construire_requetes(self, criteres: dict) -> list:
        profils = criteres.get("profils", [])
        secteurs = criteres.get("secteurs", [])
        lieux = ["Paris", "Île-de-France", "Remote"]

        requetes = []
        for profil in profils[:2]:
            for secteur in secteurs[:2]:
                requetes.append((f"{profil} {secteur}", "Paris"))
        return requetes[:3]  # Max 3 requêtes pour ne pas surcharger

    def _scraper_page(self, requete: str, lieu: str) -> list:
        params = {"q": requete, "l": lieu, "fromage": "1"}  # fromage=1 → offres des dernières 24h
        url = f"{SEARCH_URL}?{urlencode(params)}"

        try:
            response = self._get(url)
        except Exception:
            return []

        if not response:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        offres = []

        # Indeed change régulièrement son HTML — plusieurs sélecteurs en cascade
        cartes = (
            soup.select("div.job_seen_beacon")
            or soup.select("div.jobsearch-SerpJobCard")
            or soup.select("div[data-jk]")
            or soup.select("li.css-5lfssm")
        )

        for carte in cartes[:15]:
            try:
                titre_el = (
                    carte.select_one("h2.jobTitle span[title]")
                    or carte.select_one("h2.jobTitle")
                    or carte.select_one("a[data-jk] span")
                    or carte.select_one("h2")
                )
                titre = titre_el.get_text(strip=True) if titre_el else ""

                entreprise_el = (
                    carte.select_one("span.companyName")
                    or carte.select_one("[data-testid='company-name']")
                    or carte.select_one(".company")
                )
                entreprise = entreprise_el.get_text(strip=True) if entreprise_el else ""

                lieu_el = (
                    carte.select_one("div.companyLocation")
                    or carte.select_one("[data-testid='text-location']")
                    or carte.select_one(".location")
                )
                lieu_offre = lieu_el.get_text(strip=True) if lieu_el else lieu

                lien_el = carte.select_one("a[id^='job_'], a[data-jk], h2 a")
                href = lien_el.get("href", "") if lien_el else ""
                lien = href if href.startswith("http") else f"https://fr.indeed.com{href}"

                description_el = carte.select_one(".job-snippet, .summary")
                description = description_el.get_text(strip=True) if description_el else titre

                if not titre:
                    continue

                offres.append(
                    self.normaliser(
                        titre=titre,
                        entreprise=entreprise,
                        lieu=lieu_offre,
                        type_contrat="CDI/CDD",
                        url=lien,
                        description=description,
                        source=self.nom,
                    )
                )
            except Exception as e:
                logger.debug("[Indeed] Erreur parsing carte : %s", e)

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
