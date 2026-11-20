"""
FANTÔMES-01 — Test HORS RÉSEAU de la vérification des offres en ligne.

Base SQLite TEMPORAIRE, réponses HTTP SIMULÉES (aucun appel réseau). Vérifie et affiche :

  1. Classement de chacun des cas mesurés le 20/11/2026 (Free-Work par URL finale,
     HelloWork par statut HTTP) et de tous les cas INCONNU (délai, 403, 500, réseau, redirection)
  2. Sélection des offres à risque : Free-Work / HelloWork, retenues ou positionnées à la main,
     pas revues pendant le run, vérifiées il y a plus de 12 h ; BOAMP, Manuelle, non retenues,
     périmées et offres vues pendant le run JAMAIS interrogées
  3. Statuts enregistrés ; INCONNU ne masque rien
  4. Masquage d'une offre HORS LIGNE aux cinq endroits de la règle des périmées (liste, offres
     d'un candidat, compteurs, recalcul, digest) ; réapparition avec la case ; badges et fraîcheur
  5. Plafond par run et délai de politesse respectés (2 s, celui des collecteurs)
  6. Offre hors ligne retrouvée dans les listes : réhabilitée sans requête
  7. Étape 8 du pipeline (run complet) : les offres collectées pendant le run ne sont pas interrogées
  8. Aucune offre supprimée ; script de ménage en lecture seule

Usage (depuis la racine du dépôt) : python scripts/test_verification_en_ligne.py
"""

import contextlib
import hashlib
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
DB = Path(tempfile.gettempdir()) / "adh_test_en_ligne.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)              # avant tout import de src.storage
os.environ["ANTHROPIC_API_KEY"] = "factice"
os.chdir(ROOT)
logging.basicConfig(level=logging.WARNING)

import requests                                # noqa: E402
from src.storage import database               # noqa: E402
from src.verification import en_ligne          # noqa: E402
import api.database as api_db                  # noqa: E402

ECHECS = []
FW = "https://www.free-work.com/fr/tech-it/chef-de-projet-moa/job-mission/"
HW = "https://www.hellowork.com/fr-fr/emplois/"


def titre(t):
    print(f"\n=== {t}")


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


class FausseSession:
    """reponses : {url: (statut, url_finale) | exception}. Journalise chaque appel."""

    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []
        self.headers = {}

    def get(self, url, timeout=None, allow_redirects=True):
        self.appels.append({"url": url, "timeout": timeout, "allow_redirects": allow_redirects})
        rep = self.reponses.get(url, (200, url))
        if isinstance(rep, Exception):
            raise rep
        statut, finale = rep
        if not allow_redirects and finale != url:
            finale = url            # redirection non suivie : on reste sur l'URL demandée
        return types.SimpleNamespace(status_code=statut, url=finale)


def il_y_a(jours=0, heures=0):
    return (datetime.now() - timedelta(days=jours, hours=heures)).isoformat()


def section_classement():
    titre("1. Classement des cas mesurés et des cas INCONNU")
    cas = [
        ("Free-Work", FW + "chef-de-projet-sap-pm", (200, FW + "chef-de-projet-sap-pm"), "en_ligne",
         "URL finale avec /job-mission/"),
        ("Free-Work", FW + "chef-de-projet-sap-pm-2",
         (200, "https://www.free-work.com/fr/tech-it/jobs?expire=1&query=chef%20de%20projet%20sap%20pm"),
         "hors_ligne", "redirigée vers jobs?expire=1 (cas mesuré)"),
        ("Free-Work", FW + "mission-retiree", (200, "https://www.free-work.com/fr/tech-it/jobs?query=moa"),
         "hors_ligne", "redirigée hors de /job-mission/ sans expire=1"),
        ("Free-Work", FW + "bloquee", (403, FW + "bloquee"), "inconnu", "403"),
        ("Free-Work", FW + "lente", requests.exceptions.ReadTimeout("délai"), "inconnu", "délai dépassé"),
        ("HelloWork", HW + "1.html", (200, HW + "1.html"), "en_ligne", "200"),
        ("HelloWork", HW + "85107847.html", (410, HW + "85107847.html"), "hors_ligne", "410 (cas mesuré)"),
        ("HelloWork", HW + "3.html", (404, HW + "3.html"), "hors_ligne", "404"),
        ("HelloWork", HW + "4.html", (403, HW + "4.html"), "inconnu", "403"),
        ("HelloWork", HW + "5.html", (500, HW + "5.html"), "inconnu", "500"),
        ("HelloWork", HW + "6.html", (301, HW + "autre.html"), "inconnu", "redirection inattendue (301)"),
        ("HelloWork", HW + "7.html", requests.exceptions.ConnectionError("réseau"), "inconnu", "erreur réseau"),
    ]
    session = FausseSession({url: rep for _, url, rep, _, _ in cas})
    for source, url, _, attendu, libelle in cas:
        statut, detail = en_ligne.verifier_url(session, source, url)
        verifier(f"{source:<9} {libelle:<45} → {statut:<10} ({detail})", statut == attendu)
    verifier("timeout de 20 s ; Free-Work suit les redirections, HelloWork non",
             all(a["timeout"] == 20 for a in session.appels)
             and all(a["allow_redirects"] == ("free-work" in a["url"]) for a in session.appels))


def preparer_base():
    database.initialiser()
    import scripts.init_cvs_table as cvs_tbl
    import scripts.init_matchings_table as mt_tbl
    with contextlib.redirect_stdout(io.StringIO()):
        cvs_tbl.main()
        mt_tbl.main()
    database.migrer_matchings()


def inserer(nom, source, url, score, revue_jours=2, collecte_jours=5, verif=None, statut=None, revue=None):
    with database._connexion() as conn:
        cur = conn.execute(
            "INSERT INTO offres (hash, titre, entreprise, source, url, description, score_ia, date_collecte, "
            "date_derniere_vue, date_verification, statut_en_ligne) VALUES (?, ?, 'Banque', ?, ?, ?, ?, ?, ?, ?, ?)",
            (hashlib.sha1(nom.encode()).hexdigest(), nom, source, url,
             "Pilotage de projet MOA banque, Agile, Jira", score, il_y_a(collecte_jours),
             revue or il_y_a(revue_jours), verif, statut),
        )
        return cur.lastrowid


def main():
    print(f"Base temporaire : {DB}")
    print(f"Constantes : MAX_VERIFICATIONS_PAR_RUN = {en_ligne.MAX_VERIFICATIONS_PAR_RUN}, "
          f"TIMEOUT_SECONDES = {en_ligne.TIMEOUT_SECONDES}, INTERVALLE_MIN_HEURES = {en_ligne.INTERVALLE_MIN_HEURES}, "
          f"délais de politesse = { {k: v for k, v in en_ligne.delais_politesse().items() if k in en_ligne.SOURCES_VERIFIEES} }")
    section_classement()

    preparer_base()
    debut_run = il_y_a(heures=1)            # le run a commencé il y a une heure
    o = {
        "A": inserer("A Free-Work retenue", "Free-Work", FW + "a", 80),
        "B": inserer("B HelloWork retenue", "HelloWork", HW + "b.html", 75),
        "C": inserer("C revue pendant le run", "Free-Work", FW + "c", 80, revue=il_y_a(heures=0)),
        "D": inserer("D non retenue", "Free-Work", FW + "d", 30),
        "E": inserer("E positionnée à la main", "HelloWork", HW + "e.html", 30),
        "F": inserer("F BOAMP", "BOAMP", "https://www.boamp.fr/avis/detail/1", 90),
        "G": inserer("G Manuelle", "Manuelle", "https://exemple-client.fr/offre", 90),
        "H": inserer("H vérifiée il y a 3 h", "Free-Work", FW + "h", 80, verif=il_y_a(heures=3), statut="en_ligne"),
        "I": inserer("I vérifiée il y a 13 h", "Free-Work", FW + "i", 80, verif=il_y_a(heures=13), statut="en_ligne"),
        "J": inserer("J périmée (70 j)", "Free-Work", FW + "j", 80, revue_jours=1, collecte_jours=70),
    }
    with database._connexion() as conn:
        cv = conn.execute("INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat, competences_techniques, "
                          "domaines, annees_experience) VALUES ('c.pdf', 'cvs/c.pdf', 't', 'Candidate', ?, ?, 8)",
                          (json.dumps(["MOA", "Agile", "Jira"]), json.dumps(["banque"]))).lastrowid
        for nom, oid in o.items():
            conn.execute("INSERT INTO matchings (cv_id, offre_id, score_global, score_competences, score_domaine, "
                         "score_experience, score_contrat, score_lieu, details_json, date_calcul, ajout_manuel) "
                         "VALUES (?, ?, 70, 0, 0, 0, 0, 0, '{}', datetime('now'), ?)", (cv, oid, 1 if nom == "E" else 0))
    nb_avant = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM offres").fetchone()[0]

    titre("2. Sélection des offres à risque")
    reponses = {FW + "a": (200, "https://www.free-work.com/fr/tech-it/jobs?expire=1&query=a"),   # A morte
                HW + "b.html": (410, HW + "b.html"),                                              # B morte
                HW + "e.html": (403, HW + "e.html"),                                              # E inconnue
                FW + "i": (200, FW + "i")}                                                        # I vivante
    session = FausseSession(reponses)
    sommeils = []
    bilan = en_ligne.verifier_offres(debut_run, score_min=60, session=session, dormir=sommeils.append)
    interrogees = sorted(n for n, oid in o.items() if any(a["url"].endswith(n.lower()) or a["url"].endswith(f"{n.lower()}.html")
                                                           for a in session.appels))
    print(f"  offres interrogées : {interrogees}")
    print(f"  bilan : vérifiées={bilan['verifiees']} en_ligne={bilan['en_ligne']} hors_ligne={bilan['hors_ligne']} inconnu={bilan['inconnu']}")
    verifier("interrogées : A, B (retenues), E (positionnée à la main), I (vérifiée il y a 13 h)",
             interrogees == ["A", "B", "E", "I"])
    verifier("jamais interrogées : C (vue pendant le run), D (non retenue), F (BOAMP), G (Manuelle), "
             "H (vérifiée il y a 3 h), J (périmée)", not ({"C", "D", "F", "G", "H", "J"} & set(interrogees)))

    titre("3. Statuts enregistrés")
    with database._connexion() as conn:
        statuts = {n: conn.execute("SELECT statut_en_ligne, date_verification FROM offres WHERE id = ?", (oid,)).fetchone()
                   for n, oid in o.items()}
    for n in ("A", "B", "E", "I", "C"):
        print(f"  {n} : {statuts[n]['statut_en_ligne']!s:<10} vérifiée le {statuts[n]['date_verification']}")
    verifier("A, B hors ligne ; E inconnu ; I en ligne ; C non vérifiée",
             [statuts[n]["statut_en_ligne"] for n in "ABEIC"] == ["hors_ligne", "hors_ligne", "inconnu", "en_ligne", None])

    titre("4. Masquage, réapparition, badges et fraîcheur")
    ids = lambda lst, cle="id": {n for n, oid in o.items() if oid in {x[cle] for x in lst}}
    liste = api_db.get_offres_recentes()
    print(f"  liste par défaut : {sorted(ids(liste))}")
    verifier("liste : A et B (hors ligne) masquées ; E (INCONNU) visible ; J (périmée) masquée",
             not ({"A", "B", "J"} & ids(liste)) and {"C", "D", "E", "F", "G", "H", "I"} <= ids(liste))
    toutes = {x["id"]: x for x in api_db.get_offres_recentes(inclure_perimees=True)}
    verifier("case cochée : A et B réapparaissent avec hors_ligne = true (badge « Plus en ligne »), J avec perimee",
             toutes[o["A"]]["hors_ligne"] and toutes[o["B"]]["hors_ligne"] and not toutes[o["A"]]["perimee"]
             and toutes[o["J"]]["perimee"] and not toutes[o["J"]]["hors_ligne"] and not toutes[o["E"]]["hors_ligne"])
    par_cv = api_db.get_offres_par_cv(cv, score_min=30)
    verifier("offres du candidat : A, B absentes, E présente", not ({"A", "B"} & ids(par_cv, "offre_id")) and "E" in ids(par_cv, "offre_id"))
    comp = api_db.compter_candidats_par_offre(30)
    verifier("compteurs : A, B absentes", not ({o["A"], o["B"]} & set(comp)) and o["E"] in comp)
    from src.matching import calculer
    logging.getLogger("src.matching.calculer").setLevel(logging.WARNING)
    with database._connexion() as conn:
        conn.execute("UPDATE matchings SET date_calcul = '2026-01-01 00:00:00'")
    calculer.recalculer_pour_cv(cv)
    with database._connexion() as conn:
        recalc = {n for n, oid in o.items()
                  if conn.execute("SELECT date_calcul FROM matchings WHERE offre_id = ?", (oid,)).fetchone()[0] != "2026-01-01 00:00:00"}
    verifier("recalcul : A, B (hors ligne) et J (périmée) non recalculées", not ({"A", "B", "J"} & recalc) and "E" in recalc)
    hashes = {n: hashlib.sha1(x.encode()).hexdigest() for n, x in [("A", "A Free-Work retenue"), ("E", "E positionnée à la main")]}
    actifs = database.hashes_actifs(list(hashes.values()))
    verifier("digest (hashes_actifs) : A écartée, E gardée", hashes["A"] not in actifs and hashes["E"] in actifs)
    fr = {n: toutes[oid]["derniere_constatation"] for n, oid in o.items()}
    print(f"  fraîcheur constatée : I = {fr['I'][:16]} (vérifiée en ligne à l'instant), D = {fr['D'][:10]} (revue il y a 2 j), G = {fr['G']}")
    verifier("fraîcheur : vérification en ligne prise en compte, rien pour une offre Manuelle",
             fr["I"][:10] == datetime.now().isoformat()[:10] and fr["D"][:10] == il_y_a(2)[:10] and fr["G"] is None)

    titre("5. Plafond et délai de politesse")
    verifier(f"délai de politesse avant chaque requête : {sommeils} (2 s, celui de config/sources.yaml)",
             sommeils == [2, 2, 2, 2])
    extra = [inserer(f"K{i} lot", "Free-Work", FW + f"k{i}", 80) for i in range(6)]
    session2 = FausseSession({})
    sommeils2 = []
    bilan2 = en_ligne.verifier_offres(debut_run, score_min=60, limite=3, session=session2, dormir=sommeils2.append)
    print(f"  6 offres éligibles, plafond 3 : {len(session2.appels)} requête(s), plafond_atteint = {bilan2['plafond_atteint']}")
    verifier("plafond respecté (3 requêtes) et signalé ; une pause de 2 s avant chacune",
             len(session2.appels) == 3 and bilan2["plafond_atteint"] and sommeils2 == [2, 2, 2])
    bilan3 = en_ligne.verifier_offres(debut_run, score_min=60, limite=3, session=FausseSession({}), dormir=lambda s: None)
    verifier("run suivant : les 3 restantes (les vérifiées à l'instant ne sont pas reprises)",
             bilan3["verifiees"] == 3 and not bilan3["plafond_atteint"])

    titre("6. Offre hors ligne retrouvée dans les listes")
    with database._connexion() as conn:
        conn.execute("UPDATE offres SET date_derniere_vue = ? WHERE id = ?", (datetime.now().isoformat(), o["B"]))
    session4 = FausseSession({})
    bilan4 = en_ligne.verifier_offres(debut_run, score_min=60, session=session4, dormir=lambda s: None)
    with database._connexion() as conn:
        statut_b = conn.execute("SELECT statut_en_ligne FROM offres WHERE id = ?", (o["B"],)).fetchone()[0]
    verifier(f"B réhabilitée sans requête : statut {statut_b}, {bilan4['rehabilitees']} réhabilitée, "
             f"{len(session4.appels)} requête(s)", statut_b == "en_ligne" and bilan4["rehabilitees"] == 1 and not session4.appels)

    titre("7. Étape 8 du pipeline (run complet)")
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
    with database._connexion() as conn:   # tout redevient éligible sauf ce que la collecte va revoir
        conn.execute("UPDATE offres SET date_verification = NULL, statut_en_ligne = NULL")
    revue = {"titre": "D non retenue", "entreprise": "Banque", "source": "Free-Work", "lieu": "Paris",
             "type_contrat": "Freelance", "url": FW + "d", "description": "Pilotage MOA banque"}
    with database._connexion() as conn:
        conn.execute("UPDATE offres SET hash = ?, score_ia = 80 WHERE id = ?",
                     (database.get_hash("D non retenue", "Banque", "Free-Work"), o["D"]))
    session5 = FausseSession({})
    en_ligne.requests.Session = lambda: session5
    en_ligne.time.sleep = lambda s: None
    pipeline.collecter_en_parallele = lambda c, crit: ([dict(revue)], [{"nom": "Free-Work", "statut": "ok", "count": 1}])
    pipeline.construire_collecteurs = lambda cfg: []
    pipeline.charger_tous_les_cvs = lambda: []
    scan.scanner_dossier = lambda: {"ajouts": 0, "mises_a_jour": 0, "inchanges": 0, "profiles": 0}
    pipeline.digest.envoyer = lambda html_, dest, objet: False
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.run()
    urls = {a["url"] for a in session5.appels}
    print(f"  requêtes de l'étape 8 : {len(urls)} ; D (retrouvée par la collecte du run) interrogée : {FW + 'd' in urls}")
    verifier("l'offre revue par la collecte du run n'est pas interrogée ; les autres offres à risque le sont",
             FW + "d" not in urls and FW + "a" in urls and HW + "e.html" in urls)

    titre("8. Aucune suppression ; ménage en lecture seule")
    nb_apres = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM offres").fetchone()[0]
    verifier(f"offres en base : {nb_avant} au départ + 6 du lot de plafond = {nb_apres}", nb_apres == nb_avant + 6)
    inserer("Business Analyst Finance", "TEST", "https://example.com/2", None)
    empreinte = hashlib.md5(DB.read_bytes()).hexdigest()
    import scripts.offres_url_inconnues as menage
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        menage.main(["--db", str(DB)])
    print("  " + sortie.getvalue().strip().replace("\n", "\n  "))
    verifier("l'offre de test example.com/2 est signalée, l'offre Manuelle listée à part, la base intacte",
             "example.com/2" in sortie.getvalue().split("Offres « Manuelle »")[0]
             and "exemple-client.fr" in sortie.getvalue().split("Offres « Manuelle »")[1]
             and hashlib.md5(DB.read_bytes()).hexdigest() == empreinte)


if __name__ == "__main__":
    main()
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    DB.unlink(missing_ok=True)
    sys.exit(1 if ECHECS else 0)
