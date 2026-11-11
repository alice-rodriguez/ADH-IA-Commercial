"""
MANUEL-01 — Test HORS RÉSEAU de l'import manuel d'annonces.

Aucun appel réseau : Haiku est remplacé par un faux client qui renvoie une
réponse figée, la lecture de page par un faux requests.get. Tout se passe dans
une base SQLite TEMPORAIRE (la base réelle n'est pas touchée).

  1. Annonce complète (TJM, lieu…)       -> ligne offres, colonne par colonne
  2. Annonce minimale (presque rien)     -> champs absents à NULL, rien d'inventé
  3. Réponse Haiku invalide              -> offre enregistrée quand même (secours)
  4. Ré-import de l'annonce 1            -> pas de doublon, deja_presente = True
  5. Saisies refusées (422)              -> messages exacts
  6. Lien seul, page lisible (simulée)   -> texte lu, URL conservée
  7. Fenêtre de 30 jours                 -> l'offre manuelle reste listée

Usage (depuis la racine du dépôt) : python scripts/test_import_manuel.py
"""

import json
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
DB = Path(tempfile.gettempdir()) / "adh_test_import_manuel.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)          # avant tout import de src.storage
os.chdir(ROOT)

logging.basicConfig(level=logging.INFO, format="    [log] %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.storage import database                          # noqa: E402
from src.offres_manuelles import importer                 # noqa: E402

ANNONCE_COMPLETE = """Mission freelance — Chef de projet MOA Paiements SEPA (H/F)
Client : Banque Exemple SA, via notre cabinet
Lieu : Paris La Défense (92), 2 jours de télétravail par semaine
TJM : 650 à 750 € HT / jour
Démarrage : ASAP, durée 12 mois renouvelable
Au sein de la direction des moyens de paiement, vous pilotez la migration SEPA
Instant Payments : cadrage, recueil des besoins métier, coordination MOE,
recette fonctionnelle, conduite du changement. Profil confirmé, 8 ans minimum
en banque, maîtrise d'Agile et de JIRA."""

ANNONCE_MINIMALE = "Bonjour Alice, un client cherche un chef de projet, je t'en dis plus demain."

REPONSES_HAIKU = {
    "complete": json.dumps({
        "titre": "Chef de projet MOA Paiements SEPA (H/F)",
        "entreprise": "Banque Exemple SA",
        "lieu": "Paris La Défense (92)",
        "type_contrat": "Freelance",
        "tjm_min": 650,
        "tjm_max": 750,
        "description": "Au sein de la direction des moyens de paiement, pilotage de la migration "
                       "SEPA Instant Payments : cadrage, recueil des besoins métier, coordination MOE, "
                       "recette fonctionnelle, conduite du changement. Profil confirmé, 8 ans minimum "
                       "en banque, Agile, JIRA. Démarrage ASAP, 12 mois renouvelable, 2 jours de télétravail.",
    }, ensure_ascii=False),
    "minimale": json.dumps({
        "titre": "Chef de projet", "entreprise": None, "lieu": None, "type_contrat": None,
        "tjm_min": None, "tjm_max": None,
        "description": "Un client cherche un chef de projet ; détails à venir.",
    }, ensure_ascii=False),
    "invalide": "Désolé, je ne peux pas produire de JSON pour cette annonce.",
}


class FauxHaiku:
    """Remplace le client Anthropic : capture l'appel, renvoie une réponse figée."""

    def __init__(self, reponse: str):
        self.reponse, self.appels, self.messages = reponse, [], self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        bloc = type("Bloc", (), {"text": self.reponse})()
        return type("Message", (), {"content": [bloc]})()


def titre(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def afficher_ligne(offre_id):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM offres WHERE id = ?", (offre_id,)).fetchone()
    for col in row.keys():
        val = row[col]
        if isinstance(val, str) and len(val) > 110:
            val = val[:110] + f"… [{len(row[col])} car.]"
        print(f"    {col:<22}: {val!r}")
    n = conn.execute("SELECT COUNT(*) FROM matchings WHERE offre_id = ?", (offre_id,)).fetchone()[0]
    print(f"    {'(matchings calculés)':<22}: {n}")


def importer_cas(lib, url, texte, reponse):
    client = FauxHaiku(reponse)
    res = importer.importer_offre_manuelle(url, texte, client=client)
    appel = client.appels[0] if client.appels else {}
    print(f"\n  Réponse de l'import : id={res['id']}, deja_presente={res['deja_presente']}, "
          f"structuration_reussie={res['structuration_reussie']}, nb_matchings={res['nb_matchings']}")
    print(f"  Appel Haiku : model={appel.get('model')!r}, extra_body={appel.get('extra_body')!r}, "
          f"'temperature' en argument direct : {'temperature' in appel}")
    print(f"  Ligne de la table offres ({lib}) :")
    afficher_ligne(res["id"])
    return res


def preparer_base():
    database.initialiser()
    import scripts.init_cvs_table as init_cvs
    import scripts.init_matchings_table as init_matchings
    init_cvs.main()
    init_matchings.main()
    with database._connexion() as conn:
        conn.execute(
            """INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat,
               competences_techniques, domaines, annees_experience)
               VALUES ('cv_test.pdf', 'cvs/cv_test.pdf', 'texte', 'Candidat Test',
               '["Agile","Jira","SEPA"]', '["banque"]', 10)"""
        )


def main():
    print(f"Base temporaire : {DB}")
    logging.disable(logging.INFO)
    preparer_base()
    logging.disable(logging.NOTSET)

    titre("1. Annonce complète (texte collé + lien d'origine)")
    r1 = importer_cas("complète", "https://www.linkedin.com/jobs/view/123", ANNONCE_COMPLETE, REPONSES_HAIKU["complete"])

    titre("2. Annonce minimale (texte collé seul)")
    importer_cas("minimale", None, ANNONCE_MINIMALE, REPONSES_HAIKU["minimale"])

    titre("3. Réponse Haiku invalide : enregistrement de secours")
    importer_cas("secours", None, ANNONCE_COMPLETE.replace("SEPA", "SWIFT"), REPONSES_HAIKU["invalide"])

    titre("4. Ré-import de l'annonce 1 : pas de doublon")
    r4 = importer_cas("ré-import", None, ANNONCE_COMPLETE, REPONSES_HAIKU["complete"])
    n = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM offres WHERE source = 'Manuelle'").fetchone()[0]
    print(f"\n  Même id que l'import 1 : {r4['id'] == r1['id']} ; offres 'Manuelle' en base : {n}")

    titre("5. Saisies refusées (422) — messages exacts")

    class Rep:
        def __init__(self, status, text): self.status_code, self.text = status, text

    cas = [
        ("tout vide", None, "   ", None),
        ("lien sans http", "www.indeed.fr/offre/1", None, None),
        ("page HTTP 403", "https://fr.indeed.com/viewjob?jk=1", None, Rep(403, "Forbidden")),
        ("page trop courte", "https://exemple.fr/offre", None, Rep(200, "<html><body>Connectez-vous</body></html>")),
    ]
    for lib, url, texte, rep in cas:
        importer.requests.get = lambda *a, rep=rep, **k: rep
        try:
            importer.importer_offre_manuelle(url, texte, client=FauxHaiku(REPONSES_HAIKU["complete"]))
            print(f"  {lib:<18} -> ACCEPTÉ (ÉCHEC du test)")
        except importer.ImportManuelErreur as e:
            print(f"  {lib:<18} -> 422 « {e} »")

    titre("6. Lien seul, page lisible (réponse HTTP simulée)")
    page = ("<html><head><script>var x=1;</script><style>p{}</style></head><body><nav>Menu</nav>"
            f"<main><h1>Chef de projet MOA Paiements SEPA</h1><p>{ANNONCE_COMPLETE}</p></main></body></html>")
    importer.requests.get = lambda *a, **k: Rep(200, page)
    client = FauxHaiku(REPONSES_HAIKU["complete"].replace("Banque Exemple SA", "Banque Lien SA"))
    res = importer.importer_offre_manuelle("https://exemple.fr/offre/42", None, client=client)
    envoye = client.appels[0]["messages"][0]["content"].split("ANNONCE :\n", 1)[1]
    print(f"  Texte lu et envoyé à Haiku : {len(envoye)} car., scripts/styles retirés : {'var x' not in envoye}")
    print(f"  url conservée : {res['url']!r} ; id={res['id']}")

    titre("7. Fenêtre de 30 jours : l'offre manuelle reste listée")
    with database._connexion() as conn:
        conn.execute("UPDATE offres SET date_collecte = '2026-01-01T09:00:00' WHERE id = ?", (r1["id"],))
        conn.execute(
            """INSERT INTO offres (hash, titre, source, date_collecte, date_derniere_vue)
               VALUES ('vieille-fw', 'Vieille offre Free-Work', 'Free-Work', '2026-01-01T09:00:00', '2026-01-01T09:00:00')"""
        )
    from api.database import get_offres_recentes, get_candidats_par_offre
    ids = {o["id"]: o for o in get_offres_recentes(jours=30)}
    vieille_fw = sqlite3.connect(DB).execute("SELECT id FROM offres WHERE hash = 'vieille-fw'").fetchone()[0]
    print(f"  Offre manuelle datée du 01/01 listée     : {r1['id'] in ids}")
    print(f"  Offre Free-Work datée du 01/01 listée    : {vieille_fw in ids}  (comportement inchangé)")
    cands = get_candidats_par_offre(r1["id"])
    print(f"  Candidats de l'offre manuelle            : "
          f"{[(c.get('nom_candidat'), c.get('score_global')) for c in cands]}")


if __name__ == "__main__":
    main()
