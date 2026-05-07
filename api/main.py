"""
API FastAPI — ADH Veille commerciale IT.

Point d'entrée du service web exposant les offres collectées par le
pipeline de veille. Aucune dépendance à la BDD dans cette version
minimale (B.1) — les endpoints métier arrivent en B.2.

Lancement local :
    uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI

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
