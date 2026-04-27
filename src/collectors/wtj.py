"""
Collecteur Welcome to the Jungle.

Site moderne avec rendu JavaScript partiel.
On utilise leur API de recherche interne (endpoint JSON non officiel).
"""

import logging
from urllib.parse import urlencode

from .base import BaseCollector

logger = logging.getLogger(__name__)

API_URL = "https://www.welcometothejungle.com/api/v1/jobs"


class WTJCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        offres = []
        requetes = self._construire_requetes(criteres)

        for requete in requetes:
            try:
                nouvelles = self._rechercher(requete)
                offres.extend(nouvelles)
                logger.info("[WTJ] '%s' → %d offres", requete, len(nouvelles))
            except Exception as e:
                logger.error("[WTJ] Erreur pour '%s' : %s", requete, e)

        offres = self._dedupliquer(offres)
        logger.info("[WTJ] Total : %d offres uniques", len(offres))
        return offres

    def _construire_requetes(self, criteres: dict) -> list:
        profils = criteres.get("profils", [])
        return [f"{p} banque finance" for p in profils[:2]]

    def _rechercher(self, requete: str) -> list:
        params = {
            "query": requete,
            "page": 1,
            "aroundQuery": "Paris, France",
            "aroundRadius": 30,
        }
        headers = {
            **self.session.headers,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.welcometothejungle.com/fr/jobs",
        }

        try:
            response = self._get(API_URL, params=params, headers=headers)
        except Exception:
            return []

        if not response:
            return []

        try:
            data = response.json()
        except Exception:
            logger.warning("[WTJ] Réponse non-JSON")
            return []

        jobs = data.get("jobs", data.get("results", []))
        offres = []

        for job in jobs[:20]:
            try:
                titre = job.get("name", job.get("title", ""))
                entreprise = (job.get("organization") or {}).get("name", "")
                lieu = self._extraire_lieu(job)
                slug = job.get("slug", "")
                org_slug = (job.get("organization") or {}).get("slug", "")
                lien = (
                    f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}"
                    if slug else "https://www.welcometothejungle.com/fr/jobs"
                )
                description = job.get("description_plain", job.get("description", ""))[:1500]
                type_contrat = job.get("contract_type", {}).get("name", "CDI")

                if not titre:
                    continue

                offres.append(
                    self.normaliser(
                        titre=titre,
                        entreprise=entreprise,
                        lieu=lieu,
                        type_contrat=type_contrat,
                        url=lien,
                        description=description,
                        source=self.nom,
                    )
                )
            except Exception as e:
                logger.debug("[WTJ] Erreur parsing offre : %s", e)

        return offres

    @staticmethod
    def _extraire_lieu(job: dict) -> str:
        office = job.get("offices", [{}])
        if office:
            city = office[0].get("city", "")
            country = office[0].get("country", {}).get("name", "")
            return f"{city}, {country}".strip(", ")
        return "Paris"

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
