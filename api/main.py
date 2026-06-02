"""
API FastAPI — ADH Veille commerciale IT.

Point d'entrée du service web exposant les offres collectées par le
pipeline de veille. Aucune dépendance à la BDD dans cette version
minimale (B.1) — les endpoints métier arrivent en B.2.

Lancement local :
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
import json as _json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from src.auth.sessions import creer_session, supprimer_session, valider_session
from src.cv_genere.pdf import generer_pdf
from src.auth.users import (
    creer_user, get_user_par_id, get_user_par_username,
    list_users, reset_password, supprimer_user,
)
from src.auth.passwords import verify_password

logger = logging.getLogger(__name__)

from api.database import (
    compter_candidats_par_offre,
    cv_existe,
    get_all_cvs,
    get_analyse_ia,
    get_candidats_par_offre,
    get_cv_par_id,
    get_offre_par_id,
    get_offres_par_cv,
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
    CreateUserRequest,
    FavoriUpdate,
    LoginRequest,
    NotesAdhUpdate,
    NotesUpdate,
    Offre,
    OffreMatch,
    ResetPasswordRequest,
    StatutUpdate,
    UserOut,
)

VERSION = "0.1.0"

CONTACT_EMAIL_PAR_DEFAUT = "contact@adhpmconsulting.com"
CONTACT_TELEPHONE_PAR_DEFAUT = "+33 7 89 39 82 24"

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


_ROUTES_PUBLIQUES = {
    "/api/auth/login",
    "/api/auth/me",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


@app.middleware("http")
async def middleware_auth(request: Request, call_next):
    chemin = request.url.path

    # Requêtes non-API et preflight CORS passent sans auth
    if not chemin.startswith("/api/") or request.method == "OPTIONS":
        return await call_next(request)

    # Routes publiques (login, me, health…)
    if chemin in _ROUTES_PUBLIQUES:
        return await call_next(request)

    token = request.cookies.get("session_token")
    if not token:
        return JSONResponse({"detail": "Non authentifié"}, status_code=401)

    session = valider_session(token)
    if session is None:
        return JSONResponse({"detail": "Session expirée"}, status_code=401)

    request.state.user = session
    return await call_next(request)


# ── Auth ─────────────────────────────────────────────────────────────────────


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    user = get_user_par_username(body.username)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Identifiants invalides")

    token, _ = creer_session(user["id"])
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=False,  # True en production (Session H)
    )
    return {"username": user["username"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        supprimer_session(token)
    response.delete_cookie("session_token")
    return {"detail": "Déconnecté"}


@app.get("/api/auth/me")
def me(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(401, "Non authentifié")
    session = valider_session(token)
    if session is None:
        raise HTTPException(401, "Session expirée")
    return {"username": session["username"], "user_id": session["user_id"]}


# ── Utilisateurs ─────────────────────────────────────────────────────────────


@app.get("/api/users", response_model=list[UserOut])
def liste_users_endpoint():
    return list_users()


@app.post("/api/users", response_model=UserOut)
def creer_user_endpoint(body: CreateUserRequest):
    if len(body.password) < 8:
        raise HTTPException(422, "Mot de passe trop court (min 8 caractères)")
    try:
        user_id = creer_user(body.username, body.password)
        return get_user_par_id(user_id)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Ce nom d'utilisateur existe déjà")
        raise HTTPException(500, str(e))


@app.delete("/api/users/{user_id}")
def supprimer_user_endpoint(user_id: int, request: Request):
    if request.state.user["user_id"] == user_id:
        raise HTTPException(400, "Tu ne peux pas te supprimer toi-même")
    supprimer_user(user_id)
    return {"detail": "Supprimé"}


@app.post("/api/users/{user_id}/reset-password")
def reset_password_endpoint(user_id: int, body: ResetPasswordRequest):
    if len(body.new_password) < 8:
        raise HTTPException(422, "Mot de passe trop court (min 8 caractères)")
    reset_password(user_id, body.new_password)
    return {"detail": "Mot de passe réinitialisé"}


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


@app.post("/api/cvs/upload")
async def upload_cv(file: UploadFile = File(...)):
    """Upload d'un PDF : sauvegarde + extraction + profilage + matchings (SSE)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés")

    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(400, "Content-type incorrect (attendu : application/pdf)")

    contenu = await file.read()
    if len(contenu) > 10 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 10 MB)")

    cvs_dir = Path("cvs")
    cvs_dir.mkdir(exist_ok=True)
    destination = cvs_dir / file.filename
    if destination.exists():
        raise HTTPException(
            409,
            f"Un fichier nommé « {file.filename} » existe déjà. Renomme ton fichier.",
        )

    destination.write_bytes(contenu)
    nom_fichier = file.filename

    from src.cvs.ajout import ajouter_cv_depuis_pdf, profiler_un_cv
    from src.matching.calculer import recalculer_pour_cv

    def stream():
        yield "data: " + _json.dumps(
            {"step": "upload", "status": "ok",
             "message": f"Fichier sauvegardé : {nom_fichier}"},
            ensure_ascii=False,
        ) + "\n\n"

        try:
            cv_id = ajouter_cv_depuis_pdf(destination)
        except Exception as e:
            destination.unlink(missing_ok=True)
            yield "data: " + _json.dumps(
                {"step": "extract", "status": "error", "message": str(e)},
                ensure_ascii=False,
            ) + "\n\n"
            return

        yield "data: " + _json.dumps(
            {"step": "extract", "status": "ok",
             "message": f"Texte extrait et CV enregistré"},
            ensure_ascii=False,
        ) + "\n\n"

        yield "data: " + _json.dumps(
            {"step": "profile", "status": "in_progress",
             "message": "Profilage Haiku en cours..."},
            ensure_ascii=False,
        ) + "\n\n"

        try:
            profil = profiler_un_cv(cv_id)
            profil_data = {
                "nom_candidat":      profil.get("nom_candidat"),
                "titre_courant":     profil.get("titre_courant"),
                "annees_experience": profil.get("annees_experience"),
                "nb_competences":    len(profil.get("competences_techniques") or []),
                "nb_domaines":       len(profil.get("domaines") or []),
            }
        except Exception as e:
            yield "data: " + _json.dumps(
                {"step": "profile", "status": "error", "message": str(e)},
                ensure_ascii=False,
            ) + "\n\n"
            return

        yield "data: " + _json.dumps(
            {"step": "profile", "status": "ok", "data": profil_data},
            ensure_ascii=False,
        ) + "\n\n"

        yield "data: " + _json.dumps(
            {"step": "matchings", "status": "in_progress",
             "message": "Calcul des matchings..."},
            ensure_ascii=False,
        ) + "\n\n"

        try:
            nb = recalculer_pour_cv(cv_id)
        except Exception as e:
            yield "data: " + _json.dumps(
                {"step": "matchings", "status": "error", "message": str(e)},
                ensure_ascii=False,
            ) + "\n\n"
            return

        yield "data: " + _json.dumps(
            {"step": "matchings", "status": "ok", "data": {"nb_matchings": nb}},
            ensure_ascii=False,
        ) + "\n\n"

        yield "data: " + _json.dumps(
            {"step": "done", "status": "ok", "data": {"cv_id": cv_id}},
            ensure_ascii=False,
        ) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


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


@app.get("/api/cvs/{cv_id}/offres", response_model=list[OffreMatch])
def offres_pour_cv(cv_id: int, score_min: int = 30):
    """Offres matchées pour un CV donné, triées par score_global DESC."""
    try:
        if not cv_existe(cv_id):
            raise HTTPException(404, f"CV {cv_id} non trouvé")
        return get_offres_par_cv(cv_id, score_min=score_min)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur base de données : {e}")


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


@app.post("/api/cvs/{cv_id}/offres/{offre_id}/generer-cv")
def generer_cv_endpoint(cv_id: int, offre_id: int):
    """Génère un PDF CV adapté ADH pour ce couple (cv, offre) et le retourne en téléchargement."""
    if not cv_existe(cv_id):
        raise HTTPException(404, f"CV {cv_id} non trouvé")
    if not offre_existe(offre_id):
        raise HTTPException(404, f"Offre {offre_id} non trouvée")
    try:
        chemin = generer_pdf(
            cv_id=cv_id,
            offre_id=offre_id,
            contact_email=CONTACT_EMAIL_PAR_DEFAUT,
            contact_telephone=CONTACT_TELEPHONE_PAR_DEFAUT,
        )
        return FileResponse(
            chemin,
            media_type="application/pdf",
            filename=f"CV_ADH_IDADH-{cv_id:03d}_offre_{offre_id}.pdf",
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur génération CV : {e}")
