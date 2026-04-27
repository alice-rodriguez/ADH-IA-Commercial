"""
Collecteur APEC — Association Pour l'Emploi des Cadres.

L'APEC expose un endpoint de recherche utilisé par son site.
Délai de 3s entre requêtes pour respecter les serveurs.
"""

import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import BaseCollector

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.apec.fr/candidat/recherche-emploi.html/emploi"


class ApecCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        offres = []
        requetes = self._construire_requetes(criteres)

        for requete in requetes:
            try:
                nouvelles = self._scraper_page(requete)
                offres.extend(nouvelles)
                logger.info("[APEC] Requête '%s' → %d offres", requete, len(nouvelles))
            except Exception as e:
                logger.error("[APEC] Erreur pour '%s' : %s", requete, e)

        offres = self._dedupliquer(offres)
        logger.info("[APEC] Total : %d offres uniques", len(offres))
        return offres

    def _construire_requetes(self, criteres: dict) -> list:
        profils = criteres.get("profils", [])
        return [f"{p} banque assurance finance" for p in profils[:2]]

    def _scraper_page(self, requete: str) -> list:
        params = {
            "motsCles": requete,
            "lieu": "75,77,78,91,92,93,94,95",
            "typesContrat": "CDI,CDD,MIS",
            "niveauExperience": "CONFIRME,SENIOR",
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

        # Sélecteurs APEC — peuvent changer si APEC modifie son site
        cartes = soup.select("article.card-offer, div.result, li[data-jobid]")

        for carte in cartes[:20]:
            try:
                titre_el = carte.select_one("h2, h3, .title, [data-jobref]")
                titre = titre_el.get_text(strip=True) if titre_el else ""

                entreprise_el = carte.select_one(".company, .company-name, [data-company]")
                entreprise = entreprise_el.get_text(strip=True) if entreprise_el else ""

                lieu_el = carte.select_one(".location, .place, [data-location]")
                lieu = lieu_el.get_text(strip=True) if lieu_el else "Île-de-France"

                lien_el = carte.select_one("a[href]")
                href = lien_el["href"] if lien_el else ""
                lien = href if href.startswith("http") else f"https://www.apec.fr{href}"

                description_el = carte.select_one(".description, .excerpt, p")
                description = description_el.get_text(strip=True) if description_el else titre

                if not titre:
                    continue

                offres.append(
                    self.normaliser(
                        titre=titre,
                        entreprise=entreprise,
                        lieu=lieu,
                        type_contrat="CDI/CDD",
                        url=lien,
                        description=description,
                        source=self.nom,
                    )
                )
            except Exception as e:
                logger.debug("[APEC] Erreur parsing carte : %s", e)

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
