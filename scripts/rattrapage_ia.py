"""
RATTRAPAGE-01 — Rescorer les offres restées sans analyse IA.

Cas d'usage : l'IA était injoignable (crédit épuisé, clé invalide…) pendant un
ou plusieurs runs. Les offres ont été enregistrées sans score IA et la
déduplication ne les représentera jamais au pipeline.

Étapes :
  1. sélection des offres SANS score IA collectées sur les --jours derniers jours ;
  2. pré-filtre existant (src/filters/keyword_filter.py, exemptions de sources comprises) ;
  3. annonce du nombre d'offres et du coût IA estimé, puis confirmation (sauf --oui) ;
  4. filtre IA existant (src/filters/ai_filter.py) sur les offres qui passent ;
     score et résumé écrits AU FIL DE L'EAU, offre par offre ;
  5. recalcul du matching pour les offres retenues (score >= seuil).

Relançable et interruptible (Ctrl+C) sans dégât : une offre déjà rescorée a un
score en base et n'est plus sélectionnée. Une offre dont l'appel IA a échoué
n'est pas écrite : elle sera reprise au prochain lancement.

Usage (depuis la racine du dépôt) :
  py scripts/rattrapage_ia.py              (7 derniers jours, confirmation demandée)
  py scripts/rattrapage_ia.py --jours 10 --oui
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import yaml                                        # noqa: E402
from dotenv import load_dotenv                     # noqa: E402

load_dotenv()

from src.storage import database                   # noqa: E402
from src.filters import ai_filter, keyword_filter  # noqa: E402

logger = logging.getLogger("adh.rattrapage")

# Estimation par offre, aux tarifs déclarés dans ai_filter (ceux du « coût réel »
# affiché à la fin) : ~2 300 caractères de prompt (≈ 575 tokens) et ≈ 150 tokens de réponse.
TOKENS_ENTREE_ESTIMES = 575
TOKENS_SORTIE_ESTIMES = 150


def cout_estime_par_offre() -> float:
    usd = TOKENS_ENTREE_ESTIMES * ai_filter.TARIF_ENTREE + TOKENS_SORTIE_ESTIMES * ai_filter.TARIF_SORTIE
    return usd * ai_filter.EUR_USD


def charger_criteres() -> dict:
    with open(ROOT / "config" / "criteria.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def selectionner_sans_score(jours: int) -> list[dict]:
    """Offres sans score IA collectées depuis `jours` jours (les plus anciennes d'abord)."""
    limite = (datetime.now() - timedelta(days=jours)).isoformat()
    with database._connexion() as conn:
        rows = conn.execute(
            "SELECT * FROM offres WHERE score_ia IS NULL AND date_collecte >= ? "
            "ORDER BY date_collecte, id",
            (limite,),
        ).fetchall()
    return [dict(r) for r in rows]


def recalculer_matchings(offre_ids: list[int]) -> int:
    """Matching des offres retenues contre les CV profilés (même écriture que le pipeline)."""
    if not offre_ids:
        return 0
    from src.offres_manuelles.importer import calculer_matchings_offre
    total = 0
    for offre_id in offre_ids:
        try:
            total += calculer_matchings_offre(offre_id)
        except Exception as e:   # pas de table cvs / matchings : le score reste écrit
            logger.warning("Matching de l'offre %d impossible : %s", offre_id, e)
    return total


def executer(jours: int, oui: bool, demander=input) -> dict:
    """Rattrapage complet. Retourne le bilan (dict) ; `demander` est injectable pour les tests."""
    bilan = {"sans_score": 0, "passent_prefiltre": 0, "traitees": 0, "echecs": 0,
             "retenues": 0, "cout_reel": 0.0, "matchings": 0, "interrompu": False,
             "cause": None, "annule": False}

    criteres = charger_criteres()
    seuil = criteres.get("seuils", {}).get("score_ia_minimum", 60)

    sans_score = selectionner_sans_score(jours)
    bilan["sans_score"] = len(sans_score)
    print(f"Offres sans score IA collectées sur les {jours} derniers jours : {len(sans_score)}")

    candidates = keyword_filter.filtrer(sans_score, criteres)
    bilan["passent_prefiltre"] = len(candidates)
    estimation = len(candidates) * cout_estime_par_offre()
    print(f"Passent le pré-filtre (exemptions de sources comprises) : {len(candidates)}")
    print(f"Coût IA estimé : €{estimation:.4f} ({len(candidates)} appel(s) Haiku, "
          f"≈ €{cout_estime_par_offre():.5f} par offre aux tarifs déclarés dans ai_filter)")

    if not candidates:
        print("Rien à rescorer.")
        return bilan

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY n'est pas définie : aucun appel effectué.")
        bilan["annule"] = True
        return bilan

    if not oui:
        reponse = demander("Lancer le rescoring ? [o/N] ").strip().lower()
        if reponse not in ("o", "oui", "y", "yes"):
            print("Annulé : aucune offre traitée.")
            bilan["annule"] = True
            return bilan

    retenues_ids: list[int] = []

    def ecrire(offre: dict) -> None:
        """Écrit le résultat d'UNE offre dès son analyse (interruption sans perte)."""
        bilan["cout_reel"] += offre.get("cout_ia_eur", 0.0)   # cumulé ici : juste même après Ctrl+C
        if offre.get("erreur_ia"):
            return   # appel en échec : rien n'est écrit, l'offre sera reprise
        database.mettre_a_jour_ia(offre["hash"], offre.get("resume_ia", ""), offre.get("score_ia", 0))
        bilan["traitees"] += 1
        if offre.get("score_ia", 0) >= seuil:
            retenues_ids.append(offre["id"])

    rapport: dict = {}
    try:
        ai_filter.filtrer(candidates, criteres, rapport=rapport, a_chaque_offre=ecrire)
    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur : les offres déjà rescorées sont enregistrées ;"
              " relancer la commande pour traiter les autres.")
        bilan["interrompu"] = True
        bilan["cause"] = "interruption manuelle"
    bilan["echecs"] = rapport.get("echecs", 0)
    if rapport.get("interrompu"):
        bilan["interrompu"] = True
        bilan["cause"] = rapport.get("cause")

    bilan["retenues"] = len(retenues_ids)
    bilan["matchings"] = recalculer_matchings(retenues_ids)

    print()
    print(f"Traitées : {bilan['traitees']} | Retenues (score >= {seuil}) : {bilan['retenues']} | "
          f"Appels en échec : {bilan['echecs']} | Coût réel : €{bilan['cout_reel']:.4f}")
    print(f"Matchings recalculés pour les offres retenues : {bilan['matchings']}")
    if bilan["interrompu"]:
        print(f"⚠ RATTRAPAGE INCOMPLET — {bilan['cause']}. Relancer la commande une fois le problème corrigé.")
    return bilan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rescorer les offres restées sans analyse IA.")
    ap.add_argument("--jours", type=int, default=7, help="fenêtre de collecte en jours (défaut : 7)")
    ap.add_argument("--oui", action="store_true", help="ne pas demander de confirmation")
    args = ap.parse_args(argv)
    if args.jours < 1:
        ap.error("--jours doit être >= 1")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%H:%M:%S", handlers=[logging.StreamHandler(sys.stdout)])
    # Journal de calibrage du pré-filtre (une ligne par rejet) : inutile ici
    logging.getLogger("src.filters.keyword_filter").setLevel(logging.WARNING)

    database.initialiser()
    bilan = executer(args.jours, args.oui)
    return 2 if bilan["interrompu"] else 0


if __name__ == "__main__":
    sys.exit(main())
