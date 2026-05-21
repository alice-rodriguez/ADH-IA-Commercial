"""
API FastAPI — ADH Veille commerciale IT.

Point d'entrée du service web exposant les offres collectées par le
pipeline de veille. Aucune dépendance à la BDD dans cette version
minimale (B.1) — les endpoints métier arrivent en B.2.

Lancement local :
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from api.database import (
    compter_candidats_par_offre,
    cv_existe,
    get_all_cvs,
    get_analyse_ia,
    get_candidats_par_offre,
    get_cv_par_id,
    get_offre_par_id,
    get_offres_recentes,
    get_top_score_par_offre,
    maj_favori,
    maj_notes,
    maj_notes_adh,
    maj_statut,
    marquer_vue,
    offre_existe,
    upsert_analyse_ia,
)
from api.schemas import (
    CV,
    AnalyseIA,
    CandidatMatch,
    FavoriUpdate,
    NotesAdhUpdate,
    NotesUpdate,
    Offre,
    StatutUpdate,
)

VERSION = "0.1.0"

app = FastAPI(
    title="ADH Veille — API",
    description="API du pipeline de veille de missions IT pour ADH PM Consulting",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "adh-veille-api",
        "version": VERSION,
    }


@app.get("/api/offres", response_model=list[Offre])
def liste_offres():
    try:
        return get_offres_recentes(jours=30)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données : {e}")


@app.get("/api/offres/compteurs-candidats")
def compteurs_candidats(score_min: int = 30):
    """Retourne {offre_id: {nb, top_score}} pour les badges sur les cartes.

    Format : {"1": {"nb": 2, "top": 59}, "5": {"nb": 1, "top": 47}, ...}
    """
    try:
        if score_min < 0 or score_min > 100:
            raise HTTPException(422, "score_min doit être dans [0, 100]")
        compteurs = compter_candidats_par_offre(score_min)
        tops = get_top_score_par_offre(score_min)
        return {
            offre_id: {"nb": nb, "top": tops.get(offre_id, 0)}
            for offre_id, nb in compteurs.items()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.get("/api/offres/{offre_id}", response_model=Offre)
def detail_offre(offre_id: int):
    try:
        offre = get_offre_par_id(offre_id)
        if offre is None:
            raise HTTPException(status_code=404, detail=f"Offre {offre_id} non trouvée")
        return offre
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données : {e}")


def _verifier_et_recharger(offre_id: int) -> Offre:
    """Vérifie l'existence + retourne l'offre rechargée."""
    if not offre_existe(offre_id):
        raise HTTPException(404, f"Offre {offre_id} non trouvée")
    offre = get_offre_par_id(offre_id)
    if offre is None:  # race condition très improbable
        raise HTTPException(404, f"Offre {offre_id} non trouvée")
    return offre


@app.patch("/api/offres/{offre_id}/vue", response_model=Offre)
def patch_vue(offre_id: int):
    try:
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        marquer_vue(offre_id)
        return _verifier_et_recharger(offre_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.patch("/api/offres/{offre_id}/favori", response_model=Offre)
def patch_favori(offre_id: int, body: FavoriUpdate):
    try:
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        maj_favori(offre_id, body.favori)
        return _verifier_et_recharger(offre_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.patch("/api/offres/{offre_id}/statut", response_model=Offre)
def patch_statut(offre_id: int, body: StatutUpdate):
    try:
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        maj_statut(offre_id, body.statut)
        return _verifier_et_recharger(offre_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.patch("/api/offres/{offre_id}/notes", response_model=Offre)
def patch_notes(offre_id: int, body: NotesUpdate):
    try:
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        maj_notes(offre_id, body.notes)
        return _verifier_et_recharger(offre_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.get("/api/offres/{offre_id}/candidats", response_model=list[CandidatMatch])
def candidats_pour_offre(offre_id: int, limit: int = 20):
    """Retourne les CVs matchés pour une offre, triés par score_global DESC."""
    try:
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        return get_candidats_par_offre(offre_id, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


# ── CVs ───────────────────────────────────────────────────────────────────────


@app.get("/api/cvs", response_model=list[CV])
def liste_cvs():
    """Retourne tous les CVs (profilage + Notes ADH)."""
    try:
        return get_all_cvs()
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.get("/api/cvs/{cv_id}", response_model=CV)
def detail_cv(cv_id: int):
    """Retourne un CV par son id."""
    try:
        cv = get_cv_par_id(cv_id)
        if cv is None:
            raise HTTPException(404, f"CV {cv_id} non trouvé")
        return cv
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


# ── Analyses IA ──────────────────────────────────────────────────────────────


@app.get("/api/cvs/{cv_id}/offres/{offre_id}/analyse-ia", response_model=Optional[AnalyseIA])
def get_analyse_ia_endpoint(cv_id: int, offre_id: int):
    """Retourne l'analyse IA stockée, ou null si absente."""
    try:
        if not cv_existe(cv_id):
            raise HTTPException(404, f"CV {cv_id} non trouvé")
        if not offre_existe(offre_id):
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        return get_analyse_ia(cv_id, offre_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


@app.post("/api/cvs/{cv_id}/offres/{offre_id}/analyse-ia", response_model=AnalyseIA)
def post_analyse_ia_endpoint(cv_id: int, offre_id: int):
    """Lance une nouvelle analyse IA (Haiku) et la stocke (UPSERT)."""
    try:
        cv = get_cv_par_id(cv_id)
        if cv is None:
            raise HTTPException(404, f"CV {cv_id} non trouvé")
        offre = get_offre_par_id(offre_id)
        if offre is None:
            raise HTTPException(404, f"Offre {offre_id} non trouvée")
        from src.matching.analyse_ia import analyser_couple
        analyse = analyser_couple(cv, offre)
        if analyse is None:
            raise HTTPException(503, "L'analyse IA a échoué (API indisponible ou clé manquante)")
        upsert_analyse_ia(cv_id, offre_id, analyse)
        stored = get_analyse_ia(cv_id, offre_id)
        return stored
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur : {e}")


@app.patch("/api/cvs/{cv_id}/notes-adh", response_model=CV)
def patch_notes_adh(cv_id: int, body: NotesAdhUpdate):
    """Met à jour les Notes ADH d'un CV."""
    try:
        if not cv_existe(cv_id):
            raise HTTPException(404, f"CV {cv_id} non trouvé")
        notes = body.model_dump(exclude_unset=True)
        if not notes:
            raise HTTPException(422, "Aucun champ à mettre à jour")
        maj_notes_adh(cv_id, notes)
        # Recalcul des matchings (postes_cibles peut avoir changé)
        try:
            from src.matching.calculer import recalculer_pour_cv
            recalculer_pour_cv(cv_id)
        except Exception as e:
            logger.warning("Recalcul matchings échoué pour CV %d : %s", cv_id, e)
        cv = get_cv_par_id(cv_id)
        if cv is None:
            raise HTTPException(500, "CV introuvable après mise à jour")
        return cv
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")
