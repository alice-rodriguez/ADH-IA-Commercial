"""
HYGIÈNE B — Test HORS RÉSEAU du remplacement du CV d'un candidat depuis l'interface.

Base SQLite TEMPORAIRE et dossier de travail TEMPORAIRE (ni la base réelle ni cvs/ ne
sont touchés). Profilage Haiku SIMULÉ. Vrais PDF générés (WeasyPrint), vraie extraction
(pdfplumber), vrai endpoint (TestClient). Vérifie et affiche :

  1. Remplacement : aucun second candidat, même nom de fichier, nouveau texte, nouveau profil,
     ancien PDF archivé dans cvs/_remplaces/, matching recalculé
  2. Aucune saisie manuelle perdue (commentaires ADH, postes ciblés, profil personnalisé, notes
     d'expériences, statut, TJM, disponibilité, mobilité, prospect) ; nom corrigé à la main gardé
  3. Nom NON corrigé à la main : mis à jour par le profilage
  4. Échec du profilage : signalé (200, profilage_reussi = false), fichier et texte conservés
  5. PDF illisible : 422, rien n'est modifié ; fichier non PDF : 400 ; candidat inconnu : 404
  6. Un scan du dossier après remplacement ne crée pas de doublon et ne re-profile pas

Usage (depuis la racine du dépôt) : python scripts/test_remplacement_cv.py
"""

import contextlib
import io
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
TRAVAIL = Path(tempfile.mkdtemp(prefix="adh_test_remplacement_"))
DB = TRAVAIL / "test.db"
os.environ["DB_PATH"] = str(DB)              # avant tout import de src.storage
os.environ["ANTHROPIC_API_KEY"] = "factice"  # le profilage est simulé
os.chdir(ROOT)
logging.basicConfig(level=logging.WARNING)

from weasyprint import HTML                    # noqa: E402
from src.storage import database               # noqa: E402
import src.cvs.profilage as profilage          # noqa: E402
import scripts.init_cvs_table as cvs_tbl       # noqa: E402
import scripts.init_matchings_table as mt_tbl  # noqa: E402
from fastapi.testclient import TestClient      # noqa: E402
import api.main as m                           # noqa: E402

ECHECS = []
CHAMPS_MANUELS = ["commentaires_adh", "postes_cibles", "profil_adh", "notes_experiences", "statut_relation",
                  "tjm_negocie", "salaire_negocie", "disponibilite", "mobilite", "est_prospect",
                  "date_dernier_contact"]


def titre(t):
    print(f"\n=== {t}")


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


def pdf(texte: str) -> bytes:
    corps = "".join(f"<p>{ligne}</p>" for ligne in texte.split("\n"))
    return HTML(string=f"<html><body style='font:11pt Arial'>{corps}</body></html>").write_pdf()


PDF_V1 = pdf("ANCIEN CV — Jean Dupont\nChef de projet junior, 3 ans d'expérience en assurance.\n"
             "Compétences : MS Project, recette fonctionnelle, rédaction de cahiers des charges.")
PDF_V2 = pdf("NOUVEAU CV 2026 — Jean Dupont\nChef de projet MOA senior, 9 ans d'expérience en banque.\n"
             "Compétences : pilotage de programme, SEPA, Agile, Jira, conduite du changement.")

profils_appels = []


def profil_simule(texte):
    profils_appels.append(texte[:40])
    nouveau = "NOUVEAU CV" in texte
    return {"nom_candidat": "JEAN DUPONT (extrait du PDF)", "titre_courant": "Chef de projet MOA senior" if nouveau else "Chef de projet junior",
            "competences_techniques": ["Pilotage de programme", "SEPA", "Agile", "Jira"] if nouveau else ["MS Project"],
            "domaines": ["banque"] if nouveau else ["assurance"], "annees_experience": 9 if nouveau else 3,
            "types_contrat_souhaites": ["Freelance"], "localisation_preferee": "Paris", "tjm_moyen": 650, "salaire_souhaite": None}


def ligne_cv(cv_id):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return dict(conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone())


def creer_candidat(nom_fichier, nom, nom_manuel):
    (TRAVAIL / "cvs").mkdir(exist_ok=True)
    (TRAVAIL / "cvs" / nom_fichier).write_bytes(PDF_V1)
    with database._connexion() as conn:
        cur = conn.execute(
            """INSERT INTO cvs (nom_fichier, chemin_relatif, texte_brut, nom_candidat, titre_courant,
                   competences_techniques, domaines, annees_experience, date_modification_fichier,
                   nom_modifie_manuellement, commentaires_adh, postes_cibles, profil_adh, notes_experiences,
                   statut_relation, tjm_negocie, salaire_negocie, disponibilite, mobilite, est_prospect,
                   date_dernier_contact)
               VALUES (?, ?, 'ANCIEN CV texte', ?, 'Chef de projet junior', '["MS Project"]', '["assurance"]', 3, ?,
                   ?, 'Très bon contact, relancer en janvier', 'Chef de projet MOA ; PMO',
                   'Profil personnalisé rédigé par Alice', 'Mission AXA : détail ajouté à la main',
                   'place', 620, NULL, 'Immédiate', 'IDF', 1, '2026-11-10')""",
            (nom_fichier, f"cvs/{nom_fichier}", nom, (TRAVAIL / "cvs" / nom_fichier).stat().st_mtime, nom_manuel),
        )
        return cur.lastrowid


def main():
    print(f"Dossier de travail temporaire : {TRAVAIL}")
    os.chdir(TRAVAIL)                          # cvs/ relatif = dossier temporaire
    database.initialiser()
    with contextlib.redirect_stdout(io.StringIO()):
        cvs_tbl.main()
        mt_tbl.main()
    database.migrer_cvs()
    database.migrer_matchings()
    with database._connexion() as conn:
        conn.execute("INSERT INTO offres (hash, titre, source, description, date_collecte, date_derniere_vue) "
                     "VALUES ('h1', 'Chef de projet MOA banque SEPA', 'Free-Work', 'Pilotage SEPA Agile Jira banque', "
                     "datetime('now'), datetime('now'))")
    profilage.profiler_cv = profil_simule
    m.valider_session = lambda token: {"user_id": 1, "username": "alice"}
    client = TestClient(m.app)
    client.cookies.set("session_token", "test")

    cv_id = creer_candidat("jean_dupont.pdf", "Jean DUPONT (corrigé par Alice)", 1)
    avant = ligne_cv(cv_id)

    titre("1. Remplacement du CV (POST /api/cvs/{id}/remplacer-cv)")
    r = client.post(f"/api/cvs/{cv_id}/remplacer-cv", files={"file": ("nouveau_cv_2026.pdf", PDF_V2, "application/pdf")})
    corps = r.json()
    print(f"  réponse : {r.status_code} profilage_reussi={corps.get('profilage_reussi')} nb_matchings={corps.get('nb_matchings')}")
    apres = ligne_cv(cv_id)
    nb_cvs = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM cvs").fetchone()[0]
    fichiers = sorted(p.name for p in (TRAVAIL / "cvs").glob("*.pdf"))
    anciens = sorted(p.name for p in (TRAVAIL / "cvs" / "_remplaces").glob("*.pdf"))
    print(f"  candidats en base : {nb_cvs} ; cvs/ : {fichiers} ; cvs/_remplaces/ : {anciens}")
    verifier("aucun second candidat (1 seul en base, même id)", nb_cvs == 1 and r.status_code == 200 and corps["cv"]["id"] == cv_id)
    verifier("fichier écrit sous le nom existant (jean_dupont.pdf), pas sous le nom déposé",
             fichiers == ["jean_dupont.pdf"] and (TRAVAIL / "cvs" / "jean_dupont.pdf").read_bytes() == PDF_V2)
    verifier("ancien PDF archivé dans cvs/_remplaces/", len(anciens) == 1
             and (TRAVAIL / "cvs" / "_remplaces" / anciens[0]).read_bytes() == PDF_V1)
    verifier("texte ré-extrait du nouveau PDF", "NOUVEAU CV 2026" in apres["texte_brut"] and "ANCIEN" not in apres["texte_brut"])
    verifier("profil mis à jour (titre, compétences, années)",
             apres["titre_courant"] == "Chef de projet MOA senior" and json.loads(apres["competences_techniques"])[1] == "SEPA"
             and apres["annees_experience"] == 9)
    verifier("matching recalculé pour ce candidat", corps["matching_reussi"] and corps["nb_matchings"] == 1)

    titre("2. Saisies manuelles préservées")
    for champ in CHAMPS_MANUELS + ["nom_candidat"]:
        print(f"  {champ:<22} avant = {avant[champ]!r:<45} après = {apres[champ]!r}")
    verifier("toutes les saisies ADH identiques", all(avant[c] == apres[c] for c in CHAMPS_MANUELS))
    verifier("nom corrigé à la main conservé (nom_modifie_manuellement = 1)",
             apres["nom_candidat"] == "Jean DUPONT (corrigé par Alice)" and apres["nom_modifie_manuellement"] == 1)

    titre("3. Nom non corrigé à la main")
    cv2 = creer_candidat("marie_martin.pdf", "Nom extrait de l'ancien PDF", 0)
    r = client.post(f"/api/cvs/{cv2}/remplacer-cv", files={"file": ("cv.pdf", PDF_V2, "application/pdf")})
    verifier(f"nom mis à jour par le profilage : {ligne_cv(cv2)['nom_candidat']!r}",
             r.status_code == 200 and ligne_cv(cv2)["nom_candidat"] == "JEAN DUPONT (extrait du PDF)")

    titre("4. Échec du profilage")
    cv3 = creer_candidat("paul_durand.pdf", "Paul DURAND", 1)
    profilage.profiler_cv = lambda texte: None          # profiler_cv renvoie None en cas d'échec Haiku
    r = client.post(f"/api/cvs/{cv3}/remplacer-cv", files={"file": ("cv.pdf", PDF_V2, "application/pdf")})
    profilage.profiler_cv = profil_simule
    corps = r.json()
    l3 = ligne_cv(cv3)
    print(f"  réponse : {r.status_code} profilage_reussi={corps['profilage_reussi']} erreur={corps['erreur_profilage']!r}")
    verifier("échec signalé sans erreur HTTP", r.status_code == 200 and corps["profilage_reussi"] is False and corps["erreur_profilage"])
    verifier("fichier déposé conservé et texte mis à jour",
             (TRAVAIL / "cvs" / "paul_durand.pdf").read_bytes() == PDF_V2 and "NOUVEAU CV 2026" in l3["texte_brut"])
    verifier("profil précédent conservé", l3["titre_courant"] == "Chef de projet junior")

    titre("5. Refus sans modification")
    avant_illisible = ligne_cv(cv_id)
    contenu_avant = (TRAVAIL / "cvs" / "jean_dupont.pdf").read_bytes()
    r_ill = client.post(f"/api/cvs/{cv_id}/remplacer-cv", files={"file": ("vide.pdf", b"%PDF-1.4 corrompu", "application/pdf")})
    r_txt = client.post(f"/api/cvs/{cv_id}/remplacer-cv", files={"file": ("cv.docx", b"xx", "application/octet-stream")})
    r_404 = client.post("/api/cvs/9999/remplacer-cv", files={"file": ("cv.pdf", PDF_V2, "application/pdf")})
    print(f"  PDF illisible : {r_ill.status_code} {r_ill.json()['detail']!r}")
    print(f"  fichier non PDF : {r_txt.status_code} ; candidat inconnu : {r_404.status_code}")
    verifier("PDF illisible : 422, fichier et base inchangés", r_ill.status_code == 422
             and (TRAVAIL / "cvs" / "jean_dupont.pdf").read_bytes() == contenu_avant and ligne_cv(cv_id) == avant_illisible)
    verifier("non PDF : 400 ; candidat inconnu : 404", r_txt.status_code == 400 and r_404.status_code == 404)

    titre("6. Scan du dossier après remplacement")
    import src.cvs.scan as scan
    scan.profiler_cv = profil_simule
    profils_appels.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        stats = scan.scanner_dossier()
    nb_cvs = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM cvs").fetchone()[0]
    print(f"  scan : {stats} ; candidats en base : {nb_cvs} ; profilages relancés : {len(profils_appels)}")
    verifier("aucun doublon, aucun re-profilage (fichiers vus comme inchangés)",
             nb_cvs == 3 and stats["ajouts"] == 0 and stats["mises_a_jour"] == 0 and not profils_appels)


if __name__ == "__main__":
    try:
        main()
    finally:
        os.chdir(ROOT)
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    import shutil
    shutil.rmtree(TRAVAIL, ignore_errors=True)
    sys.exit(1 if ECHECS else 0)
