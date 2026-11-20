"""
MATCH-01 — Matching AVANT / APRÈS sur la VRAIE base, en LECTURE SEULE.

"AVANT" = src/matching/scoring.py ET src/matching/utils.py tels qu'au commit --ref (lus via git),
"APRÈS" = le moteur du répertoire de travail. Les deux sont recalculés pour chaque couple
(CV profilé × offre affichable) : les scores stockés en base ne sont ni lus ni modifiés.

Affiche :
  a) le classement complet AVANT et APRÈS pour l'offre --offre (défaut 5260), sous-scores compris ;
  b) la distribution des scores globaux par tranches de dix (et au-dessus du seuil d'affichage 30) ;
  c) les dix couples qui progressent le plus et les dix qui reculent le plus ;
  d) le nombre de couples dont le score ne change pas ;
  e) les CV dont le champ « postes ciblés » est vide (critère neutre) : à remplir par Alice.

Usage (depuis la racine du dépôt) :
  py scripts\\test_matching.py --db data\\offers.db
  py scripts\\test_matching.py --db data\\offers.db --ref c56a28b --offre 5260
"""

import argparse
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REF_AVANT = "c56a28b"   # dernier commit avant MATCH-01
SEUIL_AFFICHAGE = 30
CRITERES_AVANT = ["competences", "domaine", "experience", "contrat", "lieu"]
CRITERES_APRES = ["postes", "competences", "domaine", "experience", "contrat", "lieu"]


def _git_show(ref: str, chemin: str) -> str:
    try:
        return subprocess.run(["git", "show", f"{ref}:{chemin}"], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout
    except Exception as e:
        sys.exit(f"Impossible de lire {chemin} au commit {ref} via git : {e}")


def charger_moteur_avant(ref: str):
    """Ancien scoring.py exécuté contre l'ancien utils.py (tous deux lus dans git)."""
    utils = types.ModuleType("matching_utils_avant")
    utils.__file__ = str(ROOT / "src" / "matching" / "utils.py")   # utils localise config/ depuis __file__
    exec(compile(_git_show(ref, "src/matching/utils.py"), "utils_avant.py", "exec"), utils.__dict__)
    scoring = types.ModuleType("matching_scoring_avant")
    scoring.__file__ = str(ROOT / "src" / "matching" / "scoring.py")
    sauvegarde = sys.modules.get("src.matching.utils")
    sys.modules["src.matching.utils"] = utils
    try:
        exec(compile(_git_show(ref, "src/matching/scoring.py"), "scoring_avant.py", "exec"), scoring.__dict__)
    finally:
        if sauvegarde is not None:
            sys.modules["src.matching.utils"] = sauvegarde
        else:
            del sys.modules["src.matching.utils"]
    return scoring


def ouvrir_lecture_seule(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def offres_affichables(conn) -> list[dict]:
    """Même ensemble que le recalcul du matching : offres ni périmées ni hors ligne."""
    from src.storage.database import SOURCES_SANS_REVISITE, bornes_fraicheur
    revue_min, collecte_min = bornes_fraicheur()
    colonnes = {r[1] for r in conn.execute("PRAGMA table_info(offres)")}
    hors_ligne = "AND COALESCE(statut_en_ligne, '') != 'hors_ligne'" if "statut_en_ligne" in colonnes else ""
    marques = ", ".join("?" for _ in SOURCES_SANS_REVISITE)
    rows = conn.execute(
        f"SELECT * FROM offres WHERE (source IN ({marques}) OR (COALESCE(date_derniere_vue, date_collecte) >= ? "
        f"AND date_collecte >= ?)) {hors_ligne}",
        [*SOURCES_SANS_REVISITE, revue_min, collecte_min],
    ).fetchall()
    return [dict(r) for r in rows]


def sous_scores(resultat: dict, criteres: list[str]) -> dict:
    d = json.loads(resultat.get("details_json") or "{}")
    neutres = set(d.get("neutres", []))
    sortie = {}
    for c in criteres:
        if c in neutres:
            sortie[c] = None
        elif c == "postes":
            sortie[c] = d.get("score_postes")
        else:
            sortie[c] = resultat.get(f"score_{c}")
    return sortie


def fmt(v) -> str:
    return "  —" if v is None else f"{v:>3}"


def nom_cv(cv: dict) -> str:
    return (cv.get("nom_candidat") or cv.get("nom_fichier") or f"CV {cv['id']}")[:26]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=REF_AVANT, help="commit de la version AVANT du moteur")
    ap.add_argument("--db", default=None, help="base (défaut : DB_PATH ou data/offers.db)")
    ap.add_argument("--offre", type=int, default=5260, help="offre dont afficher le classement complet")
    args = ap.parse_args()

    db = Path(args.db or os.environ.get("DB_PATH") or ROOT / "data" / "offers.db")
    if not db.exists():
        sys.exit(f"Base introuvable : {db}")
    os.environ["DB_PATH"] = str(db)
    os.chdir(ROOT)

    avant = charger_moteur_avant(args.ref)
    from src.matching import scoring as apres

    conn = ouvrir_lecture_seule(db)
    cvs = [dict(r) for r in conn.execute("SELECT * FROM cvs WHERE competences_techniques IS NOT NULL ORDER BY id")]
    offres = offres_affichables(conn)
    offre_cible = conn.execute("SELECT * FROM offres WHERE id = ?", (args.offre,)).fetchone()
    conn.close()

    print("=" * 110)
    print(f"MATCH-01 — AVANT = moteur @ {args.ref} | APRÈS = répertoire de travail — base {db.resolve()} (lecture seule)")
    print(f"{len(cvs)} CV profilés × {len(offres)} offres affichables = {len(cvs) * len(offres)} couples")
    print(f"Poids APRÈS : {apres.POIDS} (critère neutre : poids redistribué)")
    print("=" * 110)

    # a) Offre cible
    print(f"\na) CLASSEMENT POUR L'OFFRE {args.offre}")
    if offre_cible is None:
        print(f"   Offre {args.offre} introuvable dans la base.")
    else:
        o = dict(offre_cible)
        print(f"   « {o.get('titre')} » — {o.get('entreprise') or '?'} — {o.get('lieu') or 'lieu ?'} — {o.get('type_contrat_clarifie') or o.get('type_contrat') or 'contrat ?'}")
        lignes = []
        for cv in cvs:
            ra, rp = avant.calculer_score_global(cv, o), apres.calculer_score_global(cv, o)
            lignes.append((cv, ra, rp))
        for titre_bloc, cle, criteres in (("AVANT", 1, CRITERES_AVANT), ("APRÈS", 2, CRITERES_APRES)):
            print(f"\n   {titre_bloc}")
            entete = "   rang  cv   candidat                    global  " + " ".join(f"{c[:6]:>6}" for c in criteres)
            print(entete + ("   palier / postes trouvés" if cle == 2 else ""))
            for rang, (cv, ra, rp) in enumerate(sorted(lignes, key=lambda x: -x[cle]["score_global"]), 1):
                r = (ra, rp)[cle - 1]
                ss = sous_scores(r, criteres)
                suite = ""
                if cle == 2:
                    d = json.loads(r["details_json"])
                    suite = f"   {d['palier']} ; {', '.join(d['postes_cibles_trouves']) or '—'} ; lieu : {d['lieu_explication']}"
                print(f"   {rang:>4}  {cv['id']:>3}  {nom_cv(cv):<26}  {r['score_global']:>5}   "
                      + " ".join(f"{fmt(ss[c]):>6}" for c in criteres) + suite)

    # Calcul de tous les couples
    couples = []
    for cv in cvs:
        for o in offres:
            couples.append((cv, o, avant.calculer_score_global(cv, o)["score_global"],
                            apres.calculer_score_global(cv, o)))

    # b) Distribution
    print("\nb) DISTRIBUTION DES SCORES GLOBAUX (tranches de dix)")
    tranche = lambda s: min(s // 10, 9)
    da = Counter(tranche(a) for _, _, a, _ in couples)
    dp = Counter(tranche(p["score_global"]) for _, _, _, p in couples)
    print(f"   {'tranche':<10} {'AVANT':>8} {'APRÈS':>8}")
    for t in range(10):
        print(f"   {f'{t*10}-{t*10+9 if t < 9 else 100}':<10} {da[t]:>8} {dp[t]:>8}")
    na = sum(1 for _, _, a, _ in couples if a >= SEUIL_AFFICHAGE)
    np_ = sum(1 for _, _, _, p in couples if p["score_global"] >= SEUIL_AFFICHAGE)
    print(f"   {'>= ' + str(SEUIL_AFFICHAGE):<10} {na:>8} {np_:>8}   (couples au-dessus du seuil d'affichage)")

    # c) Plus grands mouvements
    mouvements = sorted(couples, key=lambda x: x[3]["score_global"] - x[2])
    def ligne(cv, o, a, p):
        d = json.loads(p["details_json"])
        return (f"   {a:>3} → {p['score_global']:>3} ({p['score_global'] - a:+4})  CV {cv['id']:>3} {nom_cv(cv):<26} "
                f"| offre {o['id']:>5} {(o.get('titre') or '')[:45]:<45} | {d['palier']}")
    print("\nc) LES DIX COUPLES QUI PROGRESSENT LE PLUS")
    for c in reversed(mouvements[-10:]):
        print(ligne(*c))
    print("\n   LES DIX COUPLES QUI RECULENT LE PLUS")
    for c in mouvements[:10]:
        print(ligne(*c))

    # d) Inchangés
    inchanges = sum(1 for _, _, a, p in couples if a == p["score_global"])
    print(f"\nd) COUPLES DONT LE SCORE NE CHANGE PAS : {inchanges} sur {len(couples)}")
    # e) Postes ciblés vides
    vides = [cv for cv in cvs if not apres.postes_cibles(cv)]
    print(f"\ne) CV DONT LE CHAMP « POSTES CIBLÉS » EST VIDE : {len(vides)} sur {len(cvs)}")
    print("   (critère neutre pour eux : le moteur ne peut pas s'appuyer sur le signal le plus fiable)")
    for cv in vides:
        print(f"   CV {cv['id']:>3}  {nom_cv(cv):<26}  {cv.get('titre_courant') or ''}")
    print("\nAucune écriture en base.")


if __name__ == "__main__":
    main()
