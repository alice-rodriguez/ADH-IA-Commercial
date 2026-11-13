"""
CV-02 — Test HORS RÉSEAU des instructions de génération de CV persistantes.

Base SQLite TEMPORAIRE (la base réelle n'est pas touchée), aucun appel réseau
ni IA. Vérifie et affiche :

  1. Migration de la table parametres : idempotente (trois appels, un seul log)
  2. Lecture d'un défaut absent : chaîne vide, sans erreur
  3. Enregistrement puis relecture (et remplacement)
  4. Endpoints GET / PUT via le TestClient de FastAPI, sans puis avec session
  5. Une modification ponctuelle (instructions envoyées à la génération, non
     enregistrées) ne change pas la valeur stockée

Usage (depuis la racine du dépôt) : python scripts/test_parametres.py
"""

import logging
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = Path(tempfile.gettempdir()) / "adh_test_parametres.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)          # avant tout import de src.storage
os.chdir(ROOT)

journal = []


class _Capture(logging.Handler):
    def emit(self, record):
        journal.append(record.getMessage())
        print(f"    [log] {record.getMessage()}")


logging.basicConfig(level=logging.INFO, handlers=[_Capture()])

from src.storage import database          # noqa: E402

CLE = "cv_instructions_defaut"
ECHECS = []


def titre(t):
    print(f"\n=== {t}")


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


def valeur_en_base():
    row = sqlite3.connect(DB).execute("SELECT valeur FROM parametres WHERE cle = ?", (CLE,)).fetchone()
    return None if row is None else row[0]


def main():
    print(f"Base temporaire : {DB}")

    titre("1. Migration idempotente de la table parametres (trois appels)")
    for i in range(1, 4):
        print(f"  appel {i} de migrer_parametres()")
        database.migrer_parametres()
    logs_migration = [m for m in journal if "table parametres créée" in m]
    verifier(f"un seul log de création ({len(logs_migration)})", len(logs_migration) == 1)
    schema = sqlite3.connect(DB).execute("PRAGMA table_info(parametres)").fetchall()
    print(f"  schéma : {[(c[1], c[2], 'PK' if c[5] else '') for c in schema]}")
    verifier("colonnes cle TEXT PK, valeur TEXT",
             [(c[1], c[2], c[5]) for c in schema] == [("cle", "TEXT", 1), ("valeur", "TEXT", 0)])
    database.initialiser()   # initialiser() l'appelle aussi : toujours un seul log
    logs_migration = [m for m in journal if "table parametres créée" in m]
    verifier(f"après initialiser() : toujours un seul log ({len(logs_migration)})", len(logs_migration) == 1)
    verifier("aucune valeur pré-remplie en base", valeur_en_base() is None)

    titre("2. Lecture d'un défaut absent")
    v = database.get_parametre(CLE, "")
    print(f"  get_parametre({CLE!r}) -> {v!r}")
    verifier("chaîne vide, sans erreur", v == "")

    titre("3. Enregistrement puis relecture")
    texte1 = "Mettre en avant la conduite du changement.\nTon sobre, verbes d'action."
    database.set_parametre(CLE, texte1)
    v = database.get_parametre(CLE, "")
    print(f"  relu : {v!r}")
    verifier("relecture identique (retour à la ligne conservé)", v == texte1)
    texte2 = "Insister sur le pilotage budgétaire."
    database.set_parametre(CLE, texte2)
    nb = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM parametres WHERE cle = ?", (CLE,)).fetchone()[0]
    print(f"  après remplacement : {database.get_parametre(CLE)!r}, {nb} ligne(s) pour la clé")
    verifier("remplacement, une seule ligne", database.get_parametre(CLE) == texte2 and nb == 1)

    titre("4a. Endpoints SANS session")
    logging.disable(logging.INFO)
    try:
        from fastapi.testclient import TestClient
        import api.main as m
    except Exception as e:
        print(f"  TestClient indisponible ({type(e).__name__}: {e}) — sections 4 et 5 non exécutées")
        ECHECS.append("TestClient indisponible")
        return
    anonyme = TestClient(m.app)
    r = anonyme.get("/api/parametres/cv-instructions-defaut")
    print(f"  GET sans session -> {r.status_code} {r.json()}")
    verifier("GET refusé (401)", r.status_code == 401)
    r = anonyme.put("/api/parametres/cv-instructions-defaut", json={"valeur": "pirate"})
    print(f"  PUT sans session -> {r.status_code} {r.json()}")
    verifier("PUT refusé (401), valeur inchangée", r.status_code == 401 and valeur_en_base() == texte2)

    titre("4b. Endpoints AVEC session")
    m.valider_session = lambda token: {"user_id": 1, "username": "alice"}   # session simulée
    client = TestClient(m.app)
    client.cookies.set("session_token", "test")
    r = client.get("/api/parametres/cv-instructions-defaut")
    print(f"  GET -> {r.status_code} {r.json()}")
    verifier("GET renvoie la valeur stockée", r.status_code == 200 and r.json() == {"valeur": texte2})
    texte3 = "Valoriser les missions bancaires récentes."
    r = client.put("/api/parametres/cv-instructions-defaut", json={"valeur": texte3})
    print(f"  PUT -> {r.status_code} {r.json()}")
    verifier("PUT enregistre et renvoie la nouvelle valeur",
             r.status_code == 200 and r.json() == {"valeur": texte3} and valeur_en_base() == texte3)
    r = client.put("/api/parametres/cv-instructions-defaut", json={})
    print(f"  PUT corps sans 'valeur' -> {r.status_code} {r.json()}")
    verifier("corps sans valeur = défaut vidé", r.status_code == 200 and valeur_en_base() == "")
    r = client.get("/api/parametres/cv-instructions-defaut")
    print(f"  GET après vidage -> {r.status_code} {r.json()}")
    verifier("défaut vide relu comme chaîne vide", r.json() == {"valeur": ""})
    client.put("/api/parametres/cv-instructions-defaut", json={"valeur": texte3})

    titre("5. Modification ponctuelle non enregistrée (génération simulée)")
    recu = {}

    def faux_draft(**kw):
        recu.update(kw)
        return "draft-test", "fr", "POINTS FORTS"

    m.cv_existe = lambda cv_id: True
    m.offre_existe = lambda offre_id: True
    m.generer_pdf_draft = faux_draft
    ponctuel = texte3 + "\nPour cette offre : citer le projet SEPA."
    r = client.post("/api/cvs/1/offres/1/preview-cv", json={
        "contact_email": "contact@exemple.fr", "contact_telephone": "+33 1 00 00 00 00",
        "langue": "fr", "instructions": ponctuel})
    print(f"  POST preview-cv avec instructions modifiées -> {r.status_code}")
    verifier("la génération reçoit les instructions modifiées",
             r.status_code == 200 and recu.get("instructions_supplementaires") == ponctuel)
    print(f"  valeur stockée après génération : {valeur_en_base()!r}")
    verifier("la valeur stockée n'a pas changé", valeur_en_base() == texte3)
    r = client.get("/api/parametres/cv-instructions-defaut")
    verifier("GET (« Rétablir le défaut ») renvoie toujours le défaut", r.json() == {"valeur": texte3})


if __name__ == "__main__":
    main()
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    DB.unlink(missing_ok=True)
    sys.exit(1 if ECHECS else 0)
