"""
HYGIÈNE A — Test HORS RÉSEAU du masquage des offres périmées.

Base SQLite TEMPORAIRE (la base réelle n'est pas touchée), aucun appel réseau ni IA réel.
Offres fabriquées de fraîcheurs différentes :

  F1  collectée il y a 5 j,   revue hier            → active
  F2  collectée il y a 40 j,  revue il y a 30 j     → PÉRIMÉE (non revue depuis > 21 j)
  F3  collectée il y a 70 j,  revue hier            → PÉRIMÉE (collectée il y a > 60 j)
  F4  « Manuelle » de mai (190 j), jamais revue      → active (source exemptée)
  F5  collectée il y a 59 j,  revue il y a 20 j     → active (juste sous les deux seuils)

Démontre, pour chacun des cinq points de la portée, que F2 et F3 sont masquées,
que F4 reste visible, et que « inclure les périmées » les fait réapparaître :
  1. liste des offres            2. offres d'un candidat (get_offres_par_cv)
  3. compteurs des cartes        4. recalcul du matching
  5. digest quotidien (run complet du pipeline, collecte et IA simulées)
  + les endpoints de l'API (TestClient) ; aucune ligne supprimée en base.

Usage (depuis la racine du dépôt) : python scripts/test_fraicheur_offres.py
"""

import contextlib
import io
import json
import logging
import os
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = Path(tempfile.gettempdir()) / "adh_test_fraicheur.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)              # avant tout import de src.storage
os.environ["ANTHROPIC_API_KEY"] = "factice"  # client IA simulé
os.chdir(ROOT)
logging.basicConfig(level=logging.WARNING)

from src.storage import database               # noqa: E402
import api.database as api_db                  # noqa: E402

ECHECS = []
DESC = "Mission de pilotage de projet MOA dans le secteur bancaire, banque de détail, conduite du changement."


def titre(t):
    print(f"\n=== {t}")


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


def il_y_a(jours):
    return (datetime.now() - timedelta(days=jours)).isoformat()


OFFRES = {  # nom: (source, âge de collecte, dernière revue)
    "F1": ("Free-Work", 5, 1),
    "F2": ("Free-Work", 40, 30),
    "F3": ("HelloWork", 70, 1),
    "F4": ("Manuelle", 190, 190),
    "F5": ("Free-Work", 59, 20),
}
ACTIVES, PERIMEES = {"F1", "F4", "F5"}, {"F2", "F3"}


def preparer() -> tuple[dict, int]:
    database.initialiser()
    import scripts.init_cvs_table as cvs_tbl
    import scripts.init_matchings_table as mt_tbl
    with contextlib.redirect_stdout(io.StringIO()):
        cvs_tbl.main()
        mt_tbl.main()
    database.migrer_matchings()
    ids = {}
    with database._connexion() as conn:
        for nom, (source, age, revue) in OFFRES.items():
            cur = conn.execute(
                "INSERT INTO offres (hash, titre, entreprise, source, description, date_collecte, date_derniere_vue) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (database.get_hash(f"Chef de projet MOA banque {nom}", "Banque", source),
                 f"Chef de projet MOA banque {nom}", "Banque", source, DESC, il_y_a(age), il_y_a(revue)),
            )
            ids[nom] = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat, competences_techniques, "
            "domaines, annees_experience) VALUES ('alice.pdf', 'cvs/alice.pdf', 'texte', 'Candidate Test', ?, ?, 8)",
            (json.dumps(["MOA", "Pilotage", "Agile"]), json.dumps(["banque"])),
        )
        cv_id = cur.lastrowid
        # Anciens matchings, comme ceux qu'Alice voyait : les offres périmées en TÊTE (95)
        for nom, oid in ids.items():
            score = 95 if nom in PERIMEES else 50
            conn.execute(
                "INSERT INTO matchings (cv_id, offre_id, score_global, score_competences, score_domaine, "
                "score_experience, score_contrat, score_lieu, details_json, date_calcul, ajout_manuel) "
                "VALUES (?, ?, ?, 0, 0, 0, 0, 0, '{}', '2026-05-15 08:00:00', ?)",
                (cv_id, oid, score, 1 if nom == "F2" else 0),   # F2 : positionnement manuel ancien
            )
    return ids, cv_id


def noms(liste_ids, ids):
    inverse = {v: k for k, v in ids.items()}
    return sorted(inverse[i] for i in liste_ids if i in inverse)


def main():
    print(f"Base temporaire : {DB}")
    print(f"Seuils : JOURS_SANS_REVUE_MAX = {database.JOURS_SANS_REVUE_MAX}, AGE_MAX_JOURS = {database.AGE_MAX_JOURS}, "
          f"sources exemptées = {database.SOURCES_SANS_REVISITE}")
    ids, cv_id = preparer()

    titre("0. Règle de fraîcheur appliquée aux offres fabriquées")
    with database._connexion() as conn:
        lignes = {r["titre"][-2:]: dict(r) for r in conn.execute("SELECT * FROM offres")}
    for nom in OFFRES:
        print(f"  {nom} : {'PÉRIMÉE' if database.est_perimee(lignes[nom]) else 'active'}")
    verifier("F2 et F3 périmées, F1, F4 (Manuelle) et F5 actives",
             {n for n in OFFRES if database.est_perimee(lignes[n])} == PERIMEES)

    titre("1. Liste des offres (get_offres_recentes)")
    liste = api_db.get_offres_recentes()
    toutes = api_db.get_offres_recentes(inclure_perimees=True)
    print(f"  par défaut : {noms([o['id'] for o in liste], ids)}")
    print(f"  inclure_perimees : {[(n, o['perimee']) for n, o in sorted((k, o) for o in toutes for k, v in ids.items() if v == o['id'])]}")
    verifier("par défaut : F1, F4, F5 seulement (F4 Manuelle de mai visible)", noms([o["id"] for o in liste], ids) == sorted(ACTIVES))
    verifier("inclure_perimees : les 5, F2 et F3 marquées perimee",
             len(toutes) == 5 and {n for o in toutes for n, v in ids.items() if v == o["id"] and o["perimee"]} == PERIMEES)

    titre("2. Offres d'un candidat (get_offres_par_cv) — le cas vu par Alice")
    par_cv = api_db.get_offres_par_cv(cv_id, score_min=30)
    print(f"  ordre affiché : {[(n, o['score_global']) for o in par_cv for n, v in ids.items() if v == o['offre_id']]}")
    verifier("les anciens matchings à 95 (F2, F3) ne remontent plus, positionnement manuel F2 compris",
             noms([o["offre_id"] for o in par_cv], ids) == sorted(ACTIVES))
    tout_cv = api_db.get_offres_par_cv(cv_id, score_min=30, inclure_perimees=True)
    verifier("inclure_perimees : les 5 réapparaissent", len(tout_cv) == 5)

    titre("3. Compteurs des cartes d'offres")
    c = api_db.compter_candidats_par_offre(30)
    t = api_db.get_top_score_par_offre(30)
    print(f"  compteurs : {noms(c.keys(), ids)} ; top scores : {noms(t.keys(), ids)}")
    verifier("compteurs et top scores sans F2 ni F3", noms(c.keys(), ids) == sorted(ACTIVES) == noms(t.keys(), ids))
    verifier("inclure_perimees : compteurs des 5 offres",
             len(api_db.compter_candidats_par_offre(30, inclure_perimees=True)) == 5
             and len(api_db.get_top_score_par_offre(30, inclure_perimees=True)) == 5)

    titre("4. Recalcul du matching (recalculer_pour_cv)")
    from src.matching import calculer
    logging.getLogger("src.matching.calculer").setLevel(logging.WARNING)
    n = calculer.recalculer_pour_cv(cv_id)
    with database._connexion() as conn:
        dates = {nom: conn.execute("SELECT date_calcul, score_global FROM matchings WHERE cv_id = ? AND offre_id = ?",
                                   (cv_id, oid)).fetchone() for nom, oid in ids.items()}
    for nom, r in dates.items():
        print(f"  {nom} : date_calcul = {r['date_calcul']}, score = {r['score_global']}")
    verifier(f"{n} offres recalculées : F1, F4 (Manuelle), F5", n == 3
             and all(dates[x]["date_calcul"] != "2026-05-15 08:00:00" for x in ACTIVES))
    verifier("F2, F3 non recalculées : leurs lignes restent intactes en base (masquées, pas supprimées)",
             all(dates[x]["date_calcul"] == "2026-05-15 08:00:00" and dates[x]["score_global"] == 95 for x in PERIMEES))

    titre("5. Digest quotidien (run complet du pipeline)")
    import src.main as pipeline
    import src.cvs.scan as scan
    from src.filters import ai_filter

    class FauxClient:
        def __init__(self, api_key=None):
            self.messages = self

        def create(self, **kw):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text='{"score": 85, "resume": "ok", "type_contrat_clarifie": "Freelance"}')],
                usage=types.SimpleNamespace(input_tokens=600, output_tokens=100))

    ai_filter.anthropic.Anthropic = FauxClient
    envois = []
    # Collecte simulée : F3 est RETROUVÉE sur son site (encore en ligne, mais collectée il y a 70 j),
    # plus une offre réellement nouvelle.
    collecte = [
        {"titre": "Chef de projet MOA banque F3", "entreprise": "Banque", "source": "HelloWork", "lieu": "Paris",
         "type_contrat": "Freelance", "url": "https://example.com/f3", "description": DESC},
        {"titre": "Chef de projet MOA banque NOUVELLE", "entreprise": "Banque", "source": "Free-Work", "lieu": "Paris",
         "type_contrat": "Freelance", "url": "https://example.com/n", "description": DESC},
    ]
    pipeline.collecter_en_parallele = lambda c, crit: ([dict(o) for o in collecte],
                                                         [{"nom": "Free-Work", "statut": "ok", "count": 2}])
    pipeline.construire_collecteurs = lambda cfg: []
    pipeline.charger_tous_les_cvs = lambda: []
    scan.scanner_dossier = lambda: {"ajouts": 0, "mises_a_jour": 0, "inchanges": 0, "profiles": 0}
    pipeline.digest.envoyer = lambda html_, dest, objet: envois.append((objet, html_)) or False
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.run()
    objet, corps = envois[0]
    print(f"  objet du digest : {objet}")
    print(f"  F3 dans le digest : {'OUI' if 'banque F3' in corps else 'non'} ; NOUVELLE : {'oui' if 'NOUVELLE' in corps else 'NON'}")
    verifier("F3 (revue, mais collectée il y a 70 j) écartée du digest ; la nouvelle offre présente",
             "banque F3" not in corps and "NOUVELLE" in corps and "1 nouvelle(s) offre(s)" in objet)
    with database._connexion() as conn:
        f3 = conn.execute("SELECT date_collecte, date_derniere_vue FROM offres WHERE id = ?", (ids["F3"],)).fetchone()
    verifier("F3 : date_derniere_vue mise à jour, date_collecte d'origine conservée",
             f3["date_derniere_vue"][:10] == datetime.now().isoformat()[:10] and f3["date_collecte"] == lignes["F3"]["date_collecte"])

    titre("6. Endpoints de l'API (TestClient)")
    from fastapi.testclient import TestClient
    import api.main as m
    m.valider_session = lambda token: {"user_id": 1, "username": "alice"}
    client = TestClient(m.app)
    client.cookies.set("session_token", "test")
    ids_api = lambda url: {o.get("id", o.get("offre_id")) for o in client.get(url).json()}
    base = {ids[x] for x in ACTIVES}
    verifier("GET /api/offres : sans F2 ni F3", base <= ids_api("/api/offres") and not ({ids["F2"], ids["F3"]} & ids_api("/api/offres")))
    verifier("GET /api/offres?inclure_perimees=true : F2 et F3 présentes",
             {ids["F2"], ids["F3"]} <= ids_api("/api/offres?inclure_perimees=true"))
    par_cv_api = ids_api(f"/api/cvs/{cv_id}/offres")   # + l'offre NOUVELLE, matchée par le run de la section 5
    verifier("GET /api/cvs/{id}/offres : sans F2 ni F3", base <= par_cv_api and not ({ids["F2"], ids["F3"]} & par_cv_api))
    verifier("GET /api/cvs/{id}/offres?inclure_perimees=true : F2 et F3 présentes",
             {ids["F2"], ids["F3"]} <= ids_api(f"/api/cvs/{cv_id}/offres?inclure_perimees=true"))
    comp = client.get("/api/offres/compteurs-candidats?score_min=30").json()
    verifier("GET compteurs : sans F2 ni F3", not ({str(ids["F2"]), str(ids["F3"])} & set(comp)))

    titre("7. Aucune suppression")
    with database._connexion() as conn:
        nb_offres = conn.execute("SELECT COUNT(*) FROM offres").fetchone()[0]
        nb_match = conn.execute("SELECT COUNT(*) FROM matchings WHERE offre_id IN (?, ?)", (ids["F2"], ids["F3"])).fetchone()[0]
    verifier(f"offres en base : {nb_offres} (5 + 1 nouvelle) ; matchings de F2/F3 conservés : {nb_match}",
             nb_offres == 6 and nb_match == 2)


if __name__ == "__main__":
    main()
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    DB.unlink(missing_ok=True)
    sys.exit(1 if ECHECS else 0)
