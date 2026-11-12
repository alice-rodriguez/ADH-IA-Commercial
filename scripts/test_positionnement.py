"""
MANUEL-02 — Test HORS RÉSEAU du positionnement manuel d'un candidat sur une offre.

Base SQLite TEMPORAIRE (la base réelle n'est pas touchée), aucun appel réseau
ni IA. Vérifie et affiche :

  0. Migration matchings.ajout_manuel (idempotente)
  1. Ajout d'un candidat SANS matching préexistant : ligne créée, ajout_manuel = 1,
     sous-scores identiques à un calcul direct
  2. Ajout d'un candidat AVEC matching à score faible : scores inchangés,
     seul ajout_manuel passe à 1
  3. Recalcul complet APRÈS ajout manuel (recalculer_tous, recalculer_pour_cv,
     matching d'une offre manuelle) : marque et ligne toujours là
     + contre-épreuve : l'ancien code (INSERT OR REPLACE) effaçait la marque
  4. Affichage : un candidat positionné est renvoyé même au-delà de la limite
  5. Retrait : ajout_manuel repasse à 0, la ligne et l'analyse IA demeurent
  6. Endpoints POST / DELETE via le TestClient de FastAPI, 404 compris
  7. MANUEL-02.bis : compteur de la carte offre et onglet « offres du
     candidat » — un positionnement manuel passe toujours, quel que soit le seuil

Usage (depuis la racine du dépôt) : python scripts/test_positionnement.py
"""

import contextlib
import importlib.util
import io
import json
import logging
import os
import shutil
import sqlite3
import subprocess
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
DB = Path(tempfile.gettempdir()) / "adh_test_positionnement.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)          # avant tout import de src.storage
os.chdir(ROOT)
logging.basicConfig(level=logging.INFO, format="    [log] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
for nom in ("src.matching.calculer", "src.offres_manuelles.importer", "httpx"):
    logging.getLogger(nom).setLevel(logging.WARNING)

from src.storage import database                      # noqa: E402
from src.matching import calculer                     # noqa: E402
from src.matching.scoring import calculer_score_global  # noqa: E402

REF_ANCIEN_CODE = "bba4353"   # dernier commit avant MANUEL-02 (INSERT OR REPLACE)
COLS = "score_global, score_competences, score_domaine, score_experience, score_contrat, score_lieu, date_calcul, ajout_manuel"


def titre(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def ligne(offre_id, cv_id, db=DB):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    r = conn.execute(f"SELECT {COLS} FROM matchings WHERE offre_id = ? AND cv_id = ?", (offre_id, cv_id)).fetchone()
    return dict(r) if r else None


def preparer():
    database.initialiser()
    import scripts.init_analyses_ia_table as ia
    import scripts.init_cvs_table as cvs
    import scripts.init_matchings_table as mt
    with contextlib.redirect_stdout(io.StringIO()):
        cvs.main()
        mt.main()          # schéma d'origine, SANS ajout_manuel
        ia.main()
    with database._connexion() as conn:
        for titre_o, desc in [
            ("Business Analyst / AMOA confirmé H/F", "AMOA banque, recueil des besoins, Agile, Jira, 5 ans d'expérience"),
            ("Chef de projet SI assurance", "Pilotage de programme assurance, budget, PMO, 10 ans d'expérience"),
        ]:
            conn.execute(
                "INSERT INTO offres (hash, titre, source, description, date_collecte, date_derniere_vue) "
                "VALUES (?, ?, 'Free-Work', ?, datetime('now'), datetime('now'))",
                (titre_o, titre_o, desc),
            )
        for nom, comp, dom in [
            ("Mamour FALL", ["Business Analysis", "Jira", "Agile"], ["banque"]),
            ("Candidate Assurance", ["Program Management", "Budget Planning"], ["assurance"]),
        ]:
            conn.execute(
                "INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat, competences_techniques, "
                "domaines, annees_experience) VALUES (?, ?, 'texte', ?, ?, ?, 8)",
                (f"{nom}.pdf", f"cvs/{nom}.pdf", nom, json.dumps(comp), json.dumps(dom)),
            )


def ajouter_cv_tardif():
    """CV ajouté APRÈS le calcul : aucun matching n'existe pour lui."""
    with database._connexion() as conn:
        cur = conn.execute(
            "INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat, competences_techniques, "
            "domaines, annees_experience) VALUES ('tardif.pdf', 'cvs/tardif.pdf', 'texte', 'Candidat Tardif', "
            "'[\"Jira\", \"Agile\"]', '[\"banque\"]', 4)"
        )
        return cur.lastrowid


def main():
    print(f"Base temporaire : {DB}")
    logging.disable(logging.INFO)
    preparer()
    logging.disable(logging.NOTSET)

    titre("0. Migration matchings.ajout_manuel")
    cols = lambda: [r[1] for r in sqlite3.connect(DB).execute("PRAGMA table_info(matchings)")]
    print(f"  colonne présente avant : {'ajout_manuel' in cols()}")
    database.migrer_matchings()
    print(f"  colonne présente après : {'ajout_manuel' in cols()}")
    print("  2e et 3e appels (aucun log attendu) :")
    database.migrer_matchings(); database.migrer_matchings()

    calculer.recalculer_tous()
    cv_tardif = ajouter_cv_tardif()
    from api import database as api_db

    titre("1. Ajout d'un candidat SANS matching préexistant")
    offre_ba, offre_ass = 1, 2
    print(f"  matching avant : {ligne(offre_ba, cv_tardif)}")
    deja = api_db.positionner_candidat(offre_ba, cv_tardif)
    apres = ligne(offre_ba, cv_tardif)
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    attendu = calculer_score_global(dict(conn.execute("SELECT * FROM cvs WHERE id=?", (cv_tardif,)).fetchone()),
                                    dict(conn.execute("SELECT * FROM offres WHERE id=?", (offre_ba,)).fetchone()))
    print(f"  deja_presente = {deja}")
    print(f"  ligne créée   : {apres}")
    coherent = all(apres[k] == attendu[k] for k in ("score_global", "score_competences", "score_domaine",
                                                    "score_experience", "score_contrat", "score_lieu"))
    print(f"  sous-scores identiques à calculer_score_global : {coherent} ; ajout_manuel = {apres['ajout_manuel']}")

    titre("2. Ajout d'un candidat AVEC matching à score faible")
    couples = sqlite3.connect(DB).execute(
        "SELECT offre_id, cv_id, score_global FROM matchings WHERE ajout_manuel = 0 ORDER BY score_global ASC LIMIT 1"
    ).fetchone()
    o_faible, cv_faible, _ = couples
    avant = ligne(o_faible, cv_faible)
    deja = api_db.positionner_candidat(o_faible, cv_faible)
    apres = ligne(o_faible, cv_faible)
    print(f"  couple (offre {o_faible}, CV {cv_faible})")
    print(f"  avant : {avant}")
    print(f"  après : {apres}")
    inchanges = all(avant[k] == apres[k] for k in avant if k != "ajout_manuel")
    print(f"  deja_presente = {deja} ; scores et date_calcul inchangés : {inchanges} ; ajout_manuel = {apres['ajout_manuel']}")

    # Une analyse IA existe pour ce couple (doit survivre au retrait, point 5)
    with database._connexion() as conn:
        conn.execute("INSERT INTO analyses_ia (cv_id, offre_id, score_ia, verdict) VALUES (?, ?, 71, 'Pertinent')",
                     (cv_faible, o_faible))

    titre("3. RECALCUL COMPLET APRÈS ajout manuel — test le plus important")
    copie_avant_recalcul = DB.with_name("adh_test_positionnement_ancien_code.db")
    shutil.copy(DB, copie_avant_recalcul)
    marques_avant = sqlite3.connect(DB).execute(
        "SELECT offre_id, cv_id FROM matchings WHERE ajout_manuel = 1 ORDER BY 1, 2").fetchall()
    stats = calculer.recalculer_tous()                       # étape 7 du pipeline
    calculer.recalculer_pour_cv(cv_faible)                   # upload / notes ADH
    from src.offres_manuelles.importer import calculer_matchings_offre
    calculer_matchings_offre(offre_ba)                        # import d'une offre manuelle
    marques_apres = sqlite3.connect(DB).execute(
        "SELECT offre_id, cv_id FROM matchings WHERE ajout_manuel = 1 ORDER BY 1, 2").fetchall()
    print(f"  recalculer_tous() : {stats} ; puis recalculer_pour_cv({cv_faible}) ; puis calculer_matchings_offre({offre_ba})")
    print(f"  positionnements avant recalcul : {marques_avant}")
    print(f"  positionnements après recalcul : {marques_apres}")
    print(f"  => marques conservées : {marques_avant == marques_apres}")
    print(f"  ligne (offre {o_faible}, CV {cv_faible}) après recalcul : {ligne(o_faible, cv_faible)}")

    # Contre-épreuve : l'ancien calculer.py (INSERT OR REPLACE), lu dans git au
    # dernier commit avant MANUEL-02
    try:
        source = subprocess.run(["git", "show", f"{REF_ANCIEN_CODE}:src/matching/calculer.py"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        if "INSERT OR REPLACE INTO matchings" in source:
            chemin = Path(tempfile.gettempdir()) / "calculer_ancien.py"
            chemin.write_text(source, encoding="utf-8")
            database.DB_PATH = copie_avant_recalcul
            spec = importlib.util.spec_from_file_location("calculer_ancien", chemin)
            ancien = importlib.util.module_from_spec(spec)
            logging.disable(logging.INFO)
            spec.loader.exec_module(ancien)
            ancien.recalculer_tous()
            logging.disable(logging.NOTSET)
            perdues = sqlite3.connect(copie_avant_recalcul).execute(
                "SELECT COUNT(*) FROM matchings WHERE ajout_manuel = 1").fetchone()[0]
            print(f"  Contre-épreuve, ANCIEN code (INSERT OR REPLACE) sur une copie : "
                  f"{len(marques_avant)} positionnement(s) avant, {perdues} après")
        else:
            print(f"  Contre-épreuve : {REF_ANCIEN_CODE} ne contient pas INSERT OR REPLACE, non rejouée")
    except Exception as e:
        print(f"  Contre-épreuve non rejouée : {e}")
    finally:
        database.DB_PATH = DB
        copie_avant_recalcul.unlink(missing_ok=True)

    titre("4. Affichage : un candidat positionné reste visible au-delà de la limite")
    tous = api_db.get_candidats_par_offre(o_faible, limit=20)
    limites = api_db.get_candidats_par_offre(o_faible, limit=0)
    print(f"  get_candidats_par_offre(limit=20) : {[(c['nom_candidat'], c['score_global'], c['ajout_manuel']) for c in tous]}")
    print(f"  get_candidats_par_offre(limit=0)  : {[(c['nom_candidat'], c['score_global'], c['ajout_manuel']) for c in limites]}")

    titre("5. Retrait")
    ok = api_db.retirer_positionnement(o_faible, cv_faible)
    print(f"  retirer_positionnement -> {ok}")
    print(f"  ligne après retrait : {ligne(o_faible, cv_faible)}")
    analyse = sqlite3.connect(DB).execute(
        "SELECT score_ia, verdict FROM analyses_ia WHERE cv_id = ? AND offre_id = ?", (cv_faible, o_faible)).fetchone()
    print(f"  analyse IA du couple toujours présente : {analyse}")

    titre("6. Endpoints via le TestClient de FastAPI")
    logging.disable(logging.INFO)   # journaux HTTP / weasyprint sans intérêt ici
    try:
        from fastapi.testclient import TestClient
        import api.main as m
    except Exception as e:
        print(f"  TestClient indisponible ({type(e).__name__}: {e}) — section non exécutée")
        return
    m.valider_session = lambda token: {"user_id": 1, "username": "alice"}   # session simulée
    client = TestClient(m.app)
    client.cookies.set("session_token", "test")
    cv_libre = 2 if ligne(offre_ass, 2) is None or not ligne(offre_ass, 2)["ajout_manuel"] else 1
    cas = [
        ("POST offre inexistante", "post", "/api/offres/9999/candidats", {"cv_id": 1}),
        ("POST CV inexistant", "post", f"/api/offres/{offre_ass}/candidats", {"cv_id": 9999}),
        ("POST couple existant", "post", f"/api/offres/{offre_ass}/candidats", {"cv_id": cv_libre}),
        ("POST même couple (2e fois)", "post", f"/api/offres/{offre_ass}/candidats", {"cv_id": cv_libre}),
        ("GET candidats de l'offre", "get", f"/api/offres/{offre_ass}/candidats", None),
        ("DELETE couple positionné", "delete", f"/api/offres/{offre_ass}/candidats/{cv_libre}", None),
        ("DELETE offre inexistante", "delete", f"/api/offres/9999/candidats/{cv_libre}", None),
        ("DELETE CV inexistant", "delete", f"/api/offres/{offre_ass}/candidats/9999", None),
    ]
    with database._connexion() as conn:
        conn.execute("DELETE FROM matchings WHERE offre_id = ? AND cv_id = ?", (offre_ass, cv_tardif))
    cas.append(("DELETE couple sans matching", "delete", f"/api/offres/{offre_ass}/candidats/{cv_tardif}", None))
    cas.append(("POST couple sans matching", "post", f"/api/offres/{offre_ass}/candidats", {"cv_id": cv_tardif}))
    for lib, methode, url, body in cas:
        r = getattr(client, methode)(url, json=body) if body is not None else getattr(client, methode)(url)
        corps = r.json()
        if isinstance(corps, list):
            corps = [(c["nom_candidat"], c["score_global"], c["ajout_manuel"]) for c in corps]
        elif isinstance(corps, dict) and "score_global" in corps:
            corps = {k: corps[k] for k in ("cv_id", "nom_candidat", "score_global", "score_competences",
                                           "score_domaine", "score_experience", "ajout_manuel", "deja_presente")}
        print(f"  {lib:<28} -> {r.status_code} {corps}")

    titre("7. MANUEL-02.bis — compteur de la carte et offres du candidat (seuil 30)")
    # Couple au score 0 positionné à la main : (offre 2, CV tardif), via le POST ci-dessus
    o7, cv7 = offre_ass, cv_tardif
    print(f"  couple testé : offre {o7}, CV {cv7}, matching {ligne(o7, cv7)}")
    for etat in ("positionné", "retiré"):
        if etat == "retiré":
            api_db.retirer_positionnement(o7, cv7)
        compteurs = api_db.compter_candidats_par_offre(30)
        tops = api_db.get_top_score_par_offre(30)
        offres_cv = api_db.get_offres_par_cv(cv7, score_min=30)
        r1 = client.get("/api/offres/compteurs-candidats?score_min=30").json()
        r2 = client.get(f"/api/cvs/{cv7}/offres?score_min=30").json()
        print(f"  [{etat}] compteur offre {o7} : fonction={compteurs.get(o7)} top={tops.get(o7)} ; "
              f"API={r1.get(str(o7))}")
        print(f"  [{etat}] offres du CV {cv7} (seuil 30) : fonction={[(o['offre_id'], o['score_global'], o['ajout_manuel']) for o in offres_cv]} ; "
              f"API={[(o['offre_id'], o['score_global'], o['ajout_manuel']) for o in r2]}")


if __name__ == "__main__":
    main()
