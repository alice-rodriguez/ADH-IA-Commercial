"""
RATTRAPAGE-01 — Test HORS RÉSEAU du rattrapage IA et de la protection du filtre IA.

Base SQLite TEMPORAIRE (la base réelle n'est pas touchée), client Anthropic
SIMULÉ (aucun appel réseau). Vérifie et affiche :

  1. Sélection des offres sans score IA et respect de la fenêtre --jours
  2. Confirmation refusée : aucun appel IA, rien d'écrit
  3. Rattrapage : pré-filtre (exemption BOAMP comprise), scores écrits,
     échecs d'appel NON écrits
  4. Idempotence : une relance ne rappelle pas l'IA pour les offres rescorées
  5. Interruption manuelle (Ctrl+C) en cours de route : relance = seulement le reste
  6. Protection : 10 échecs consécutifs « crédit épuisé » → arrêt après 10 appels,
     cause nommée ; clé invalide reconnue ; des échecs non consécutifs n'arrêtent pas
  7. Bilan de fin de run du pipeline : échec explicite au lieu de « 0 retenues »
  8. (bis) Tarifs Haiku 4.5 : coût réel et estimation calculés à $1 / $5 par million
  9. (bis) Clé API absente : échec explicite (aucune offre retenue), comme l'IA injoignable
 10. (ter) Mail quotidien : objet et corps en ÉCHEC si le filtre IA est interrompu
     (cause du journal, offres non analysées, commande de rattrapage), run complet compris

Usage (depuis la racine du dépôt) : python scripts/test_rattrapage_ia.py
"""

import io
import logging
import os
import sqlite3
import sys
import tempfile
import types
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = Path(tempfile.gettempdir()) / "adh_test_rattrapage.db"
DB.unlink(missing_ok=True)
os.environ["DB_PATH"] = str(DB)              # avant tout import de src.storage
os.environ["ANTHROPIC_API_KEY"] = "factice"  # le client est simulé, aucun appel réel
os.chdir(ROOT)

journal = []


class _Capture(logging.Handler):
    def emit(self, record):
        journal.append((record.levelname, record.getMessage()))


logging.basicConfig(level=logging.INFO, handlers=[_Capture()])

import anthropic                               # noqa: E402
import httpx                                   # noqa: E402
from src.storage import database               # noqa: E402
from src.filters import ai_filter              # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import rattrapage_ia                           # noqa: E402

ECHECS = []


def titre(t):
    print(f"\n=== {t}")


def verifier(libelle, condition):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {libelle}")
    if not condition:
        ECHECS.append(libelle)


# ── Client Anthropic simulé ──────────────────────────────────────────────────

class ErreurCredit(Exception):
    """Même message que l'API quand le crédit est épuisé (400)."""
    status_code = 400

    def __init__(self):
        super().__init__("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
                         "'message': 'Your credit balance is too low to access the Anthropic API.'}}")


def erreur_cle():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=req), body=None)


class FauxClient:
    """comportement(n, prompt) -> score (int) ou exception à lever ; n = numéro d'appel (1, 2, …)."""
    appels = 0
    comportement = None

    def __init__(self, api_key=None):
        self.messages = self

    def create(self, **kw):
        FauxClient.appels += 1
        res = FauxClient.comportement(FauxClient.appels, kw["messages"][0]["content"])
        if isinstance(res, BaseException):
            raise res
        texte = '{"score": %d, "resume": "Résumé simulé", "type_contrat_clarifie": "Freelance"}' % res
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=texte)],
                                     usage=types.SimpleNamespace(input_tokens=600, output_tokens=100))


ai_filter.anthropic.Anthropic = FauxClient


def score_selon_titre(n, prompt):
    return 30 if "Business Analyst" in prompt else 80


def regler(comportement):
    FauxClient.appels = 0
    FauxClient.comportement = comportement


# ── Jeu de données ───────────────────────────────────────────────────────────

def inserer(titre_offre, source="Free-Work", age_jours=0, description="", score=None):
    database.sauvegarder({"titre": titre_offre, "entreprise": "Entreprise " + titre_offre[:12], "source": source,
                          "lieu": "Paris", "type_contrat": "Freelance", "url": "https://example.com",
                          "description": description})
    date = (datetime.now() - timedelta(days=age_jours)).isoformat()
    with sqlite3.connect(DB) as c:
        c.execute("UPDATE offres SET date_collecte = ?, score_ia = ? WHERE titre = ?", (date, score, titre_offre))


DESC_OK = "Mission de pilotage de projet MOA dans le secteur bancaire, banque de détail, conduite du changement."


def scores_en_base():
    with sqlite3.connect(DB) as c:
        return {t: s for t, s in c.execute("SELECT titre, score_ia FROM offres ORDER BY id")}


def lancer(jours=7, oui=True, reponse="o"):
    sortie = io.StringIO()
    with redirect_stdout(sortie):
        bilan = rattrapage_ia.executer(jours, oui, demander=lambda _q: reponse)
    return bilan, sortie.getvalue()


def main():
    print(f"Base temporaire : {DB}")
    database.initialiser()
    logging.getLogger("src.filters.keyword_filter").setLevel(logging.WARNING)
    inserer("Chef de projet MOA banque", description=DESC_OK)                     # A : retenue
    inserer("Business Analyst banque", age_jours=3, description=DESC_OK)         # B : score 30, rejet IA
    inserer("Assistance à maîtrise d'ouvrage SI", source="BOAMP")                # C : exemptée du pré-filtre
    inserer("Développeur Java", description="Développement backend Java Spring")  # D : rejet pré-filtre
    inserer("Chef de projet MOA assurance ancienne", age_jours=10, description=DESC_OK)  # E : hors fenêtre 7 j
    inserer("Chef de projet MOA déjà notée", description=DESC_OK, score=75)      # F : déjà scorée

    titre("1. Sélection des offres sans score IA, fenêtre --jours")
    sel7 = [o["titre"] for o in rattrapage_ia.selectionner_sans_score(7)]
    sel15 = [o["titre"] for o in rattrapage_ia.selectionner_sans_score(15)]
    print(f"  --jours 7  : {sel7}")
    print(f"  --jours 15 : {sel15}")
    verifier("7 jours : A, B, C, D (ni E à 10 jours, ni F déjà scorée)",
             sorted(sel7) == sorted(["Chef de projet MOA banque", "Business Analyst banque",
                                     "Assistance à maîtrise d'ouvrage SI", "Développeur Java"]))
    verifier("15 jours : E en plus", "Chef de projet MOA assurance ancienne" in sel15 and len(sel15) == 5)
    verifier("F (déjà scorée) jamais sélectionnée", "Chef de projet MOA déjà notée" not in sel15)

    titre("2. Confirmation refusée")
    regler(score_selon_titre)
    bilan, sortie = lancer(oui=False, reponse="n")
    print("  " + sortie.strip().replace("\n", "\n  "))
    verifier("aucun appel IA, rien d'écrit", FauxClient.appels == 0 and bilan["annule"]
             and scores_en_base()["Chef de projet MOA banque"] is None)

    titre("3. Rattrapage (--jours 7 --oui)")
    regler(score_selon_titre)
    bilan, sortie = lancer()
    print("  " + sortie.strip().replace("\n", "\n  "))
    s = scores_en_base()
    print(f"  appels IA : {FauxClient.appels} ; scores en base : {s}")
    verifier("3 appels : A, B, C (D rejetée au pré-filtre, BOAMP exemptée)", FauxClient.appels == 3)
    verifier("scores écrits : A=80, B=30 (rejet IA écrit aussi), C=80",
             s["Chef de projet MOA banque"] == 80 and s["Business Analyst banque"] == 30
             and s["Assistance à maîtrise d'ouvrage SI"] == 80)
    verifier("D, E inchangées (NULL), F inchangée (75)",
             s["Développeur Java"] is None and s["Chef de projet MOA assurance ancienne"] is None
             and s["Chef de projet MOA déjà notée"] == 75)
    verifier("bilan : 3 traitées, 2 retenues, coût réel > 0",
             bilan["traitees"] == 3 and bilan["retenues"] == 2 and bilan["cout_reel"] > 0)

    titre("4. Idempotence : relance immédiate")
    regler(score_selon_titre)
    bilan, sortie = lancer()
    print("  " + sortie.strip().replace("\n", "\n  "))
    verifier("aucun appel IA à la relance", FauxClient.appels == 0 and bilan["traitees"] == 0)

    titre("5. Interruption manuelle (Ctrl+C au 3e appel) puis relance")
    for i in range(5):
        inserer(f"Chef de projet MOA banque lot {i}", description=DESC_OK)
    regler(lambda n, p: KeyboardInterrupt() if n == 3 else 80)
    bilan, sortie = lancer()
    print("  " + sortie.strip().replace("\n", "\n  "))
    lot = {k: v for k, v in scores_en_base().items() if "lot" in k}
    print(f"  après interruption : {lot}")
    verifier("2 offres écrites avant l'interruption, 3 restantes NULL",
             sum(v == 80 for v in lot.values()) == 2 and sum(v is None for v in lot.values()) == 3)
    verifier(f"coût réel des 2 appels aboutis conservé (€{bilan['cout_reel']:.5f})", bilan["cout_reel"] > 0)
    regler(score_selon_titre)
    bilan, _ = lancer()
    print(f"  relance : {FauxClient.appels} appel(s) IA")
    verifier("la relance ne traite que les 3 restantes", FauxClient.appels == 3
             and all(v == 80 for k, v in scores_en_base().items() if "lot" in k))

    titre("6a. Protection : crédit épuisé à chaque appel (15 offres)")
    for i in range(15):
        inserer(f"Chef de projet MOA banque crédit {i}", description=DESC_OK)
    regler(lambda n, p: ErreurCredit())
    journal.clear()
    bilan, sortie = lancer()
    print("  " + sortie.strip().replace("\n", "\n  "))
    erreurs = [m for niv, m in journal if "FILTRE IA INTERROMPU" in m]
    print(f"  journal : {erreurs[0] if erreurs else '(aucun)'}")
    credit = {k: v for k, v in scores_en_base().items() if "crédit" in k}
    verifier("arrêt après exactement 10 appels (5 offres jamais envoyées)", FauxClient.appels == 10)
    verifier("cause nommée : crédit API Anthropic épuisé", bilan["cause"] == "crédit API Anthropic épuisé"
             and erreurs and "crédit API Anthropic épuisé" in erreurs[0])
    verifier("aucun score écrit pour les échecs (15 NULL)", all(v is None for v in credit.values()))
    verifier("code de sortie 2 (rattrapage incomplet)", bilan["interrompu"] is True)
    regler(score_selon_titre)
    bilan, _ = lancer()
    verifier(f"crédit rétabli : la relance traite les 15 ({FauxClient.appels} appels)", FauxClient.appels == 15)

    titre("6b. Protection au niveau du filtre IA (pipeline)")
    offres = [{"titre": f"Offre {i}", "source": "Free-Work", "description": ""} for i in range(12)]
    regler(lambda n, p: erreur_cle())
    rapport = {}
    retenues, _ = ai_filter.filtrer([dict(o) for o in offres], {"seuils": {}}, rapport=rapport)
    print(f"  clé invalide : {FauxClient.appels} appels, rapport = {rapport}")
    verifier("clé invalide reconnue, arrêt après 10 appels",
             FauxClient.appels == 10 and rapport["cause"] == "clé API Anthropic invalide ou révoquée")
    regler(lambda n, p: 80 if n == 10 else ErreurCredit())   # 9 échecs, 1 succès, puis échecs
    rapport = {}
    ai_filter.filtrer([dict(o) for o in offres], {"seuils": {}}, rapport=rapport)
    print(f"  9 échecs + 1 succès + 2 échecs : {FauxClient.appels} appels, interrompu = {rapport['interrompu']}")
    verifier("des échecs non consécutifs n'interrompent pas (12 appels)",
             FauxClient.appels == 12 and rapport["interrompu"] is False)
    regler(lambda n, p: ErreurCredit() if n % 2 else erreur_cle())   # erreurs différentes en alternance
    rapport = {}
    ai_filter.filtrer([dict(o) for o in offres], {"seuils": {}}, rapport=rapport)
    verifier("des erreurs différentes en alternance n'interrompent pas", rapport["interrompu"] is False)

    titre("7. Bilan de fin de run du pipeline")
    try:
        from src.main import ligne_bilan
    except Exception as e:
        print(f"  src.main non importable ({type(e).__name__}: {e}) — section non exécutée")
        ECHECS.append("src.main non importable")
        return
    stats = {"collectees": 925, "dedup": 704, "passe1": 466, "passe2": 0}
    bilan_src = {"ok": ["A", "B", "C"], "partielles": [], "echecs": [], "vides": []}
    normal = ligne_bilan(stats, 0.0, bilan_src, {"interrompu": False})
    panne = ligne_bilan(stats, 0.0, bilan_src, {"interrompu": True, "analysees": 0,
                                               "cause": "crédit API Anthropic épuisé"})
    print(f"  sans incident : {normal}")
    print(f"  IA injoignable : {panne}")
    verifier("échec explicite et cause nommée", "ÉCHEC FILTRE IA (crédit API Anthropic épuisé)" in panne
             and "→ 0 retenues" not in panne)

    titre("8. (bis) Tarifs Haiku 4.5")
    print(f"  TARIF_ENTREE = ${ai_filter.TARIF_ENTREE * 1e6:.2f} / M tokens, "
          f"TARIF_SORTIE = ${ai_filter.TARIF_SORTIE * 1e6:.2f} / M tokens")
    verifier("constantes à $1 / $5 par million de tokens",
             abs(ai_filter.TARIF_ENTREE - 1e-6) < 1e-15 and abs(ai_filter.TARIF_SORTIE - 5e-6) < 1e-15)
    regler(lambda n, p: 80)   # réponse simulée : 600 tokens en entrée, 100 en sortie
    offre = ai_filter.analyser_offre({"titre": "Offre", "description": ""}, {}, FauxClient())
    attendu = (600 * 1.00 + 100 * 5.00) / 1e6 * ai_filter.EUR_USD
    ancien = (600 * 0.25 + 100 * 1.25) / 1e6 * ai_filter.EUR_USD
    print(f"  coût d'un appel (600 / 100 tokens) : €{offre['cout_ia_eur']:.6f} "
          f"(ancien calcul : €{ancien:.6f}, ×{offre['cout_ia_eur'] / ancien:.1f})")
    verifier("coût réel d'un appel calculé au nouveau tarif", abs(offre["cout_ia_eur"] - attendu) < 1e-12)
    estim = rattrapage_ia.cout_estime_par_offre()
    attendu_estim = (575 * 1.00 + 150 * 5.00) / 1e6 * ai_filter.EUR_USD
    print(f"  estimation du rattrapage par offre : €{estim:.6f} ; pour 466 offres : €{466 * estim:.4f}")
    verifier("estimation du rattrapage au nouveau tarif", abs(estim - attendu_estim) < 1e-12)

    titre("9. (bis) Clé API absente")
    cle = os.environ.pop("ANTHROPIC_API_KEY")
    try:
        regler(lambda n, p: 80)
        journal.clear()
        rapport = {}
        lot = [dict(o) for o in offres]
        retenues, cout = ai_filter.filtrer(lot, {"seuils": {}}, rapport=rapport)
        msg = [m for niv, m in journal if niv == "ERROR" and "FILTRE IA INTERROMPU" in m]
        print(f"  filtrer() sans clé : {len(retenues)} retenue(s) sur {len(lot)}, {FauxClient.appels} appel(s), "
              f"rapport = {rapport}")
        print(f"  journal : {msg[0] if msg else '(aucun)'}")
        verifier("aucune offre retenue (avant : toutes passaient sans score)", retenues == [] and cout == 0.0)
        verifier("filtre interrompu, cause nommée, aucun appel",
                 rapport["interrompu"] and "clé API Anthropic absente" in rapport["cause"] and FauxClient.appels == 0)
        verifier("journal en ERROR avec renvoi vers le rattrapage",
                 bool(msg) and "rattrapage_ia.py" in msg[0] and "12 offre(s)" in msg[0])
        ligne = ligne_bilan({"collectees": 925, "dedup": 704, "passe1": 466, "passe2": 0}, 0.0, bilan_src, rapport)
        print(f"  bilan : {ligne}")
        verifier("bilan de fin de run en échec explicite",
                 "ÉCHEC FILTRE IA (clé API Anthropic absente" in ligne and "rattrapage_ia.py" in ligne)
        inserer("Chef de projet MOA banque sans clé", description=DESC_OK)
        bilan, sortie = lancer()
        print("  " + sortie.strip().replace("\n", "\n  "))
        verifier("rattrapage sans clé : interrompu, cause nommée, aucun appel, rien d'écrit",
                 bilan["interrompu"] and "clé API Anthropic absente" in bilan["cause"] and FauxClient.appels == 0
                 and scores_en_base()["Chef de projet MOA banque sans clé"] is None)
    finally:
        os.environ["ANTHROPIC_API_KEY"] = cle

    titre("10. (ter) Mail quotidien")
    from src.email_digest import digest
    stats17 = {"collectees": 925, "dedup": 704, "passe1": 466, "passe2": 0}
    sources = [{"nom": "Free-Work", "statut": "ok", "count": 925}]
    date = "17/11/2026"

    def rapport_de(comportement, nb=12, sans_cle=False):
        """Rapport réellement produit par ai_filter.filtrer (même chaîne que le pipeline)."""
        regler(comportement)
        r = {}
        sauvegarde = os.environ.pop("ANTHROPIC_API_KEY") if sans_cle else None
        try:
            ai_filter.filtrer([{"titre": f"O{i}", "description": ""} for i in range(nb)], {"seuils": {}}, rapport=r)
        finally:
            if sans_cle:
                os.environ["ANTHROPIC_API_KEY"] = sauvegarde
        return r

    cas = {
        "crédit épuisé": rapport_de(lambda n, p: ErreurCredit()),
        "clé absente": rapport_de(lambda n, p: 80, sans_cle=True),
        "clé invalide": rapport_de(lambda n, p: erreur_cle()),
    }
    for nom, rapport in cas.items():
        objet = digest.construire_objet(date, 0, rapport)
        corps = digest.generer_html([], {}, stats17, 0.0, sources, rapport_ia=rapport)
        print(f"  [{nom}] objet : {objet}")
        print(f"  [{nom}] cause dans le corps : {rapport['cause']!r}")
        verifier(f"{nom} : objet en ÉCHEC, sans « aucune nouvelle offre »",
                 "ÉCHEC — le filtre IA n'a pas pu s'exécuter" in objet and "aucune nouvelle offre" not in objet)
        verifier(f"{nom} : cause du journal, 466 non analysées, commande de rattrapage",
                 rapport["cause"] in corps and "Offres restées non analysées :</b> 466" in corps
                 and r"py scripts\rattrapage_ia.py" in corps)
        verifier(f"{nom} : le corps ne dit pas « Aucune nouvelle offre »",
                 "Aucune nouvelle offre pertinente" not in corps and "Aucune offre n'a pu être évaluée" in corps)

    # Interruption en cours de route : 2 offres retenues avant l'arrêt
    regler(lambda n, p: 80 if n <= 2 else ErreurCredit())
    partiel = {}
    retenues, _ = ai_filter.filtrer([{"titre": f"Chef de projet {i}", "description": "", "type_contrat": "Freelance"}
                                  for i in range(20)], {"seuils": {}}, rapport=partiel)
    st = {"collectees": 30, "dedup": 25, "passe1": 20, "passe2": len(retenues)}
    objet = digest.construire_objet(date, len(retenues), partiel)
    corps = digest.generer_html(retenues, {}, st, 0.0, sources, rapport_ia=partiel)
    print(f"  [interruption après 2 offres] objet : {objet}")
    verifier("interruption partielle : objet en ÉCHEC, 2 offres affichées, 18 non analysées",
             "ÉCHEC" in objet and corps.count("score IA") == 2
             and "Offres restées non analysées :</b> 18" in corps)

    # Run normal : inchangé
    normal_objet = digest.construire_objet(date, 0, {"interrompu": False})
    normal_corps = digest.generer_html([], {}, stats17, 0.0, sources, rapport_ia={"interrompu": False})
    sans_rapport = digest.generer_html([], {}, stats17, 0.0, sources)
    print(f"  [run normal] objet : {normal_objet}")
    verifier("run normal sans offre : objet et corps inchangés, pas de bandeau d'échec",
             normal_objet == "[ADH Veille] 17/11/2026 — aucune nouvelle offre"
             and "Aucune nouvelle offre pertinente" in normal_corps and "ÉCHEC" not in normal_corps
             and "n'a pas pu s'exécuter" not in normal_corps
             and normal_corps == sans_rapport)
    verifier("objets normaux et [TEST] inchangés",
             digest.construire_objet(date, 3, None) == "[ADH Veille] 17/11/2026 — 3 nouvelle(s) offre(s)"
             and digest.construire_objet(date, 0, cas["clé absente"], mode_test=True).startswith("[TEST] [ADH Veille]"))
    piege = digest.generer_html([], {}, stats17, 0.0, sources,
                                rapport_ia={"interrompu": True, "analysees": 0, "cause": "autre erreur : <script>"})
    verifier("cause échappée en HTML", "<script>" not in piege and "&lt;script&gt;" in piege)

    # Run complet du pipeline (src.main.run) : collecte simulée, clé absente, envoi intercepté
    import src.main as pipeline
    import src.cvs.scan as scan
    envois = []
    pipeline.collecter_en_parallele = lambda c, crit: (
        [{"titre": "Chef de projet MOA banque run", "entreprise": "Banque X", "source": "Free-Work",
          "lieu": "Paris", "type_contrat": "Freelance", "url": "https://example.com", "description": DESC_OK}],
        [{"nom": "Free-Work", "statut": "ok", "count": 1}])
    pipeline.construire_collecteurs = lambda cfg: []
    pipeline.charger_tous_les_cvs = lambda: []
    scan.scanner_dossier = lambda: {"ajouts": 0, "mises_a_jour": 0, "inchanges": 0, "profiles": 0}
    pipeline.digest.envoyer = lambda html_, dest, objet: envois.append((objet, html_)) or False
    cle = os.environ.pop("ANTHROPIC_API_KEY")
    journal.clear()
    try:
        pipeline.run()
    finally:
        os.environ["ANTHROPIC_API_KEY"] = cle
    bilan_run = [m for niv, m in journal if niv == "ERROR" and "Pipeline :" in m]
    print(f"  [run complet] objet envoyé : {envois[0][0] if envois else '(aucun envoi)'}")
    print(f"  [run complet] bilan : {bilan_run[0].strip() if bilan_run else '(aucun)'}")
    verifier("run complet : un mail envoyé, objet en ÉCHEC, corps avec la cause et la commande",
             len(envois) == 1 and "ÉCHEC — le filtre IA n'a pas pu s'exécuter" in envois[0][0]
             and "clé API Anthropic absente" in envois[0][1] and "rattrapage_ia.py" in envois[0][1]
             and "Offres restées non analysées :</b> 1" in envois[0][1])
    verifier("run complet : bilan de fin de run en ERROR, ÉCHEC FILTRE IA",
             bool(bilan_run) and "ÉCHEC FILTRE IA (clé API Anthropic absente" in bilan_run[0])


if __name__ == "__main__":
    main()
    print()
    print("RÉSULTAT :", "TOUT OK" if not ECHECS else f"{len(ECHECS)} ÉCHEC(S) : {ECHECS}")
    DB.unlink(missing_ok=True)
    sys.exit(1 if ECHECS else 0)
