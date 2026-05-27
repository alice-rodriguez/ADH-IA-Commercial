"""
Modèles Pydantic pour la validation et la sérialisation des réponses API.
"""

from typing import Literal, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    date_creation: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class CV(BaseModel):
    """Représentation complète d'un CV (profilage Haiku + Notes ADH)."""

    id: int
    nom_fichier: str
    chemin_relatif: str

    # Métadonnées scan
    date_ajout: Optional[str] = None
    date_dernier_scan: Optional[str] = None

    # Profilage Haiku
    nom_candidat: Optional[str] = None
    titre_courant: Optional[str] = None
    competences_techniques: Optional[str] = None
    domaines: Optional[str] = None
    annees_experience: Optional[int] = None
    types_contrat_souhaites: Optional[str] = None
    localisation_preferee: Optional[str] = None
    tjm_moyen: Optional[int] = None
    salaire_souhaite: Optional[int] = None
    date_dernier_profilage: Optional[str] = None

    # Notes ADH
    tjm_negocie: Optional[int] = None
    salaire_negocie: Optional[int] = None
    postes_cibles: Optional[str] = None
    mobilite: Optional[str] = None
    disponibilite: Optional[str] = None
    commentaires_adh: Optional[str] = None
    statut_relation: Optional[str] = None
    date_dernier_contact: Optional[str] = None
    date_modif_notes_adh: Optional[str] = None


class NotesAdhUpdate(BaseModel):
    """Body du PATCH /api/cvs/{id}/notes-adh."""

    tjm_negocie: Optional[int] = None
    salaire_negocie: Optional[int] = None
    postes_cibles: Optional[str] = None
    mobilite: Optional[str] = None
    disponibilite: Optional[str] = None
    commentaires_adh: Optional[str] = None
    statut_relation: Optional[Literal['actif', 'en_pause', 'place', 'inactif']] = None
    date_dernier_contact: Optional[str] = None


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


class AnalyseIA(BaseModel):
    """Résultat d'une analyse IA pour un couple (CV, offre)."""

    score_ia: int
    verdict: str
    explication: str
    points_forts: list[str]
    points_faibles: list[str]
    questions_a_poser: list[str]
    date_analyse: Optional[str] = None


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
