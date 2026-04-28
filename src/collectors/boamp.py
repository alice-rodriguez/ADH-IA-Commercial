"""
Collecteur BOAMP — Bulletin Officiel des Annonces des Marchés Publics.

Utilise l'API REST publique Opendatasoft hébergée sur :
  https://boamp-datadila.opendatasoft.com/api/records/1.0/search/

Filtres reproduits depuis l'URL de recherche utilisateur :
  - q        : "chef de projet OR business analyst OR project manager OR MOA"
  - refine.dc: 453 (services), 163 (assistance technique et conseil)
  - refine.code_departement: 75, 77, 78, 91, 92, 93, 94, 95 (Île-de-France)
  - sort     : dateparution (les plus récentes d'abord)
"""

import logging

from .base import BaseCollector

logger = logging.getLogger(__name__)

API_URL = "https://boamp-datadila.opendatasoft.com/api/records/1.0/search/"

# Codes cpv/dc correspondant aux marchés de services intellectuels (conseil, assistance)
DC_SERVICES    = "453"
DC_ASSISTANCE  = "163"

# Départements Île-de-France
DEPARTEMENTS_IDF = ["75", "77", "78", "91", "92", "93", "94", "95"]

# Requête unique couvrant tous les profils ciblés
REQUETE_BOAMP = (
    "chef de projet OR business analyst OR project manager OR MOA OR AMOA OR PMO"
)


class BoampCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        try:
            offres = self._appeler_api()
        except Exception as e:
            logger.error("[BOAMP] Erreur lors de l'appel API : %s", e)
            raise

        logger.info("[BOAMP] %d offres uniques collectées", len(offres))
        return offres

    def _appeler_api(self) -> list[dict]:
        """
        Appelle l'API Opendatasoft BOAMP avec les filtres Île-de-France.
        Retourne la liste d'offres parsées.
        """
        # Construction des paramètres — chaque refine.code_departement est répété
        params = [
            ("dataset", "boamp"),
            ("q",       REQUETE_BOAMP),
            ("refine.dc", DC_SERVICES),
            ("refine.dc", DC_ASSISTANCE),
            ("rows",    "50"),
            ("sort",    "dateparution"),
        ]
        for dept in DEPARTEMENTS_IDF:
            params.append(("refine.code_departement", dept))

        # requests accepte une liste de tuples pour les paramètres répétés
        response = self._get(API_URL, params=params)
        if not response:
            return []

        try:
            data = response.json()
        except Exception:
            logger.error("[BOAMP] Réponse non-JSON reçue (HTTP %s)", response.status_code)
            return []

        nhits = data.get("nhits", 0)
        records = data.get("records", [])
        logger.info("[BOAMP] API : %d résultat(s) total, %d récupérés", nhits, len(records))

        return [self._parser_record(r) for r in records if self._parser_record(r)]

    def _parser_record(self, record: dict) -> dict | None:
        """Transforme un enregistrement Opendatasoft en offre normalisée."""
        fields = record.get("fields", {})

        # Titre = objet du marché
        objet = fields.get("objet", "").strip()
        if not objet:
            return None

        # Acheteur public
        acheteur_raw = fields.get("acheteur", {})
        if isinstance(acheteur_raw, dict):
            acheteur = acheteur_raw.get("nom", "")
        else:
            acheteur = str(acheteur_raw)

        # Localisation
        dept = fields.get("code_departement", "")
        lieu = f"Département {dept} (Île-de-France)" if dept else "Île-de-France"

        # URL de l'avis sur boamp.fr
        id_web = fields.get("idweb", "") or record.get("recordid", "")
        url_avis = fields.get("url_avis", f"https://www.boamp.fr/avis/detail/{id_web}")

        # Description enrichie avec dates
        date_parution = fields.get("dateparution", "")
        date_limite   = fields.get("datelimitereponse", "")
        descripteur   = fields.get("descripteur_libelle", "")

        description_parts = [objet]
        if descripteur:
            description_parts.append(f"Catégorie : {descripteur}")
        if date_parution:
            description_parts.append(f"Publié le : {date_parution}")
        if date_limite:
            description_parts.append(f"Date limite de réponse : {date_limite}")

        description = " | ".join(description_parts)

        return self.normaliser(
            titre=objet,
            entreprise=acheteur or "Acheteur public",
            lieu=lieu,
            type_contrat="Appel d'offres",
            url=url_avis,
            description=description,
            source=self.nom,
        )
