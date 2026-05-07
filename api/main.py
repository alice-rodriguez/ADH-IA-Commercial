"""
API FastAPI — ADH Veille commerciale IT.

Point d'entrée du service web exposant les offres collectées par le
pipeline de veille. Aucune dépendance à la BDD dans cette version
minimale (B.1) — les endpoints métier arrivent en B.2.

Lancement local :
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI, HTTPException

from api.database import get_offre_par_id, get_offres_recentes
from api.schemas import Offre

VERSION = "0.1.0"

app = FastAPI(
    title="ADH Veille — API",
    description="API du pipeline de veille de missions IT pour ADH PM Consulting",
    version=VERSION,
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
