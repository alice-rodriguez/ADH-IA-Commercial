"""
Modèles Pydantic pour la validation et la sérialisation des réponses API.
"""

from typing import Literal, Optional
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


class FavoriUpdate(BaseModel):
    """Body du PATCH /api/offres/{id}/favori."""

    favori: bool


class StatutUpdate(BaseModel):
    """Body du PATCH /api/offres/{id}/statut."""

    statut: Literal["nouveau", "en_cours", "envoye", "rejete"]


class NotesUpdate(BaseModel):
    """Body du PATCH /api/offres/{id}/notes. None ou chaîne vide = effacer."""

    notes: Optional[str] = None


class CandidatMatch(BaseModel):
    """Un candidat (CV) matché pour une offre."""

    cv_id: int
    nom_fichier: str
    nom_candidat: Optional[str]
    titre_courant: Optional[str]
    annees_experience: Optional[int]
    localisation_preferee: Optional[str]
    score_global: int
    score_competences: int
    score_domaine: int
    score_experience: int
    score_contrat: int
    score_lieu: int
    details_json: Optional[str]
    date_calcul: Optional[str]
