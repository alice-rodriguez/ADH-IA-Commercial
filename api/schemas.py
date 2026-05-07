"""
Modèles Pydantic pour la validation et la sérialisation des réponses API.
"""

from typing import Optional
from pydantic import BaseModel


class Offre(BaseModel):
    """Format de retour d'une offre dans les réponses de l'API."""

    id: int
    titre: str
    entreprise: Optional[str]
    lieu: Optional[str]
    type_contrat: Optional[str]
    type_contrat_clarifie: Optional[str]
    source: Optional[str]
    url: Optional[str]
    description: Optional[str]
    resume_ia: Optional[str]
    score_ia: Optional[int]
    tjm_min: Optional[int]
    tjm_max: Optional[int]
    salaire_min: Optional[int]
    salaire_max: Optional[int]
    date_collecte: str
    vue: bool
    favori: bool
    statut: str
    notes: Optional[str]
