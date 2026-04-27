"""
Collecteur BOAMP — Bulletin Officiel des Annonces des Marchés Publics.

Utilise l'API REST officielle et gratuite du BOAMP.
C'est la source la plus fiable : API publique, pas de scraping, pas de blocage.
Documentation : https://www.boamp.fr/pages/ouverture-des-donnees/
"""

import logging
from datetime import datetime, timedelta

from .base import BaseCollector

logger = logging.getLogger(__name__)

API_URL = "https://www.boamp.fr/api/search/"


class BoampCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        offres = []
        profils = criteres.get("profils", [])
        requetes = self._construire_requetes(profils)

        for requete in requetes:
            try:
                nouvelles = self._rechercher(requete)
                offres.extend(nouvelles)
                logger.info("[BOAMP] Requête '%s' → %d offres", requete, len(nouvelles))
            except Exception as e:
                logger.error("[BOAMP] Erreur pour la requête '%s' : %s", requete, e)

        offres = self._dedupliquer(offres)
        logger.info("[BOAMP] Total : %d offres uniques collectées", len(offres))
        return offres

    def _construire_requetes(self, profils: list) -> list:
        """Combine profils + secteurs pour construire plusieurs requêtes ciblées."""
        return [
            f"{profil} banque assurance finance"
            for profil in profils[:3]  # Limite pour ne pas surcharger l'API
        ]

    def _rechercher(self, requete: str) -> list:
        hier = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        params = {
            "q": requete,
            "rows": 50,
            "start": 0,
            "facet": "famille_libelle",
            "refine.famille_libelle": "Prestation de services",
        }

        try:
            response = self._get(API_URL, params=params)
        except Exception:
            return []

        if not response:
            return []

        try:
            data = response.json()
        except Exception:
            logger.warning("[BOAMP] Réponse JSON invalide")
            return []

        records = data.get("records", [])
        offres = []

        for record in records:
            fields = record.get("fields", {})
            titre = fields.get("objet", "")
            acheteur = fields.get("acheteur_nom", "")
            lieu = fields.get("lieu_execution_libelle", fields.get("departement_libelle", ""))
            url_avis = fields.get("url_avis", f"https://www.boamp.fr/avis/detail/{record.get('recordid', '')}")
            description = fields.get("descripteur_libelle", "") or fields.get("objet", "")

            if not titre:
                continue

            offres.append(
                self.normaliser(
                    titre=titre,
                    entreprise=acheteur,
                    lieu=lieu,
                    type_contrat="Appel d'offres",
                    url=url_avis,
                    description=description,
                    source=self.nom,
                )
            )

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
