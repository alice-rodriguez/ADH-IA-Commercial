"""
Classe de base pour tous les collecteurs d'offres.

Chaque source (BOAMP, APEC, Indeed…) hérite de cette classe.
Cela garantit que toutes les sources retournent des offres dans le même format.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaseCollector(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.nom = config.get("nom", "Inconnu")
        self.delai = config.get("delai_secondes", 3)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @abstractmethod
    def collecter(self, criteres: dict) -> list[dict]:
        """
        Collecte les offres depuis la source.
        Retourne une liste de dicts au format normalisé.
        criteres : le contenu de criteria.yaml
        """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
    )
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET HTTP avec retry automatique et délai de politesse."""
        time.sleep(self.delai)
        try:
            response = self.session.get(url, timeout=20, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.warning("[%s] Erreur HTTP %s sur %s", self.nom, e.response.status_code, url)
            raise
        except requests.exceptions.RequestException as e:
            logger.warning("[%s] Erreur réseau sur %s : %s", self.nom, url, e)
            raise

    @staticmethod
    def normaliser(
        titre: str,
        entreprise: str,
        lieu: str,
        type_contrat: str,
        url: str,
        description: str,
        source: str,
    ) -> dict:
        """Construit un dict d'offre dans le format standard attendu par le reste du système."""
        return {
            "titre": (titre or "").strip(),
            "entreprise": (entreprise or "").strip(),
            "lieu": (lieu or "").strip(),
            "type_contrat": (type_contrat or "").strip(),
            "url": (url or "").strip(),
            "description": (description or "").strip()[:3000],
            "source": source,
        }
