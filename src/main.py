"""
Point d'entrée principal de l'agent ADH.

Orchestration du pipeline complet :
  1. Collecte (toutes les sources en parallèle)
  2. Déduplication (base SQLite)
  3. Passe 1 — Filtre mots-clés (gratuit)
  4. Passe 2 — Filtre IA (Claude Haiku)
  5. Matching CV ↔ offres (TF-IDF, gratuit)
  6. Envoi du digest email (Microsoft Graph API)

Variable d'environnement MODE_TEST=true : injecte 2 offres fictives
pour valider le pipeline sans attendre de vraies offres.
"""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("adh.agent")

from src.storage import database
from src.collectors.boamp import BoampCollector
from src.collectors.apec import ApecCollector
from src.collectors.indeed import IndeedCollector
from src.collectors.wtj import WTJCollector
from src.collectors.freelance_com import FreelanceComCollector
from src.filters import keyword_filter, ai_filter
from src.matching.cv_parser import charger_tous_les_cvs
from src.matching.matcher import MoteurMatching
from src.email_digest import digest


OFFRES_TEST = [
    {
        "titre": "Chef de projet MOA Banque - TEST",
        "entreprise": "Banque Exemple SA",
        "lieu": "Paris (75)",
        "type_contrat": "Freelance",
        "source": "TEST",
        "url": "https://example.com/test1",
        "description": (
            "Mission freelance pour grand groupe bancaire, 3 ans d'expérience requis "
            "sur projets SI banque de détail. Compétences : Agile, JIRA, MOA, "
            "conduite du changement. Secteur bancaire et assurance."
        ),
    },
    {
        "titre": "Business Analyst Assurance - TEST",
        "entreprise": "Assurance Exemple Vie",
        "lieu": "La Défense / Remote",
        "type_contrat": "CDI",
        "source": "TEST",
        "url": "https://example.com/test2",
        "description": (
            "CDI Business Analyst pour compagnie d'assurance vie, projets de "
            "transformation digitale. PRINCE2 souhaité. Finance, asset management, "
            "mutuelle. Expérience MOA/AMOA requise."
        ),
    },
]


def charger_config() -> tuple[dict, dict]:
    base = Path(__file__).parent.parent / "config"
    with open(base / "criteria.yaml", encoding="utf-8") as f:
        criteres = yaml.safe_load(f)
    with open(base / "sources.yaml", encoding="utf-8") as f:
        sources_cfg = yaml.safe_load(f)
    return criteres, sources_cfg


def construire_collecteurs(sources_cfg: dict) -> list:
    classes = {
        "boamp":              BoampCollector,
        "apec":               ApecCollector,
        "indeed":             IndeedCollector,
        "welcometothejungle": WTJCollector,
        "freelance_com":      FreelanceComCollector,
    }
    collecteurs = []
    for cle, cfg in sources_cfg.get("sources", {}).items():
        if cfg.get("active", True) and cle in classes:
            collecteurs.append(classes[cle](cfg))
            logger.info("Source activée : %s", cfg.get("nom", cle))
    return collecteurs


def collecter_en_parallele(collecteurs: list, criteres: dict) -> tuple[list, list]:
    """
    Lance tous les collecteurs simultanément.
    Retourne (toutes_offres, resultats_sources).
    resultats_sources = [{nom, statut, count} ou {nom, statut, erreur}]
    """
    toutes_offres = []
    resultats_sources = []

    if not collecteurs:
        return toutes_offres, resultats_sources

    with ThreadPoolExecutor(max_workers=len(collecteurs)) as executor:
        futures = {executor.submit(c.collecter, criteres): c for c in collecteurs}
        for future in as_completed(futures):
            collecteur = futures[future]
            try:
                offres = future.result()
                toutes_offres.extend(offres)
                resultats_sources.append({
                    "nom": collecteur.nom,
                    "statut": "ok",
                    "count": len(offres),
                })
                logger.info("✓ %s : %d offres collectées", collecteur.nom, len(offres))
            except Exception as e:
                resultats_sources.append({
                    "nom": collecteur.nom,
                    "statut": "erreur",
                    "erreur": str(e)[:120],
                })
                logger.error("✗ %s : erreur de collecte — %s", collecteur.nom, e)

    return toutes_offres, resultats_sources


def dedupliquer_et_sauvegarder(offres: list, criteres: dict) -> tuple[list, int]:
    fenetre = criteres.get("seuils", {}).get("fenetre_deduplication_jours", 7)
    nouvelles, doublons = [], 0
    for offre in offres:
        offre["fenetre_deduplication_jours"] = fenetre
        if database.sauvegarder(offre):
            nouvelles.append(offre)
        else:
            doublons += 1
    logger.info("Déduplication : %d nouvelles, %d doublons écartés", len(nouvelles), doublons)
    return nouvelles, doublons


def run():
    mode_test = os.getenv("MODE_TEST", "false").lower() == "true"

    logger.info("=" * 60)
    logger.info(
        "Agent ADH — démarrage %s%s",
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        " [MODE TEST]" if mode_test else "",
    )
    logger.info("=" * 60)

    criteres, sources_cfg = charger_config()
    database.initialiser()

    # ── 1. Collecte ──────────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 1 : Collecte des offres ──")
    collecteurs = construire_collecteurs(sources_cfg)
    toutes_offres, resultats_sources = collecter_en_parallele(collecteurs, criteres)

    # Injection des offres fictives en mode test
    if mode_test:
        logger.info("MODE TEST : injection de %d offres fictives", len(OFFRES_TEST))
        toutes_offres.extend(OFFRES_TEST)
        resultats_sources.append({
            "nom": "TEST (offres fictives)",
            "statut": "ok",
            "count": len(OFFRES_TEST),
        })

    logger.info("Total brut collecté : %d offres", len(toutes_offres))
    stats = {"collectees": len(toutes_offres), "dedup": 0, "passe1": 0, "passe2": 0}

    # ── 2. Déduplication ─────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 2 : Déduplication ──")
    nouvelles_offres, _ = dedupliquer_et_sauvegarder(toutes_offres, criteres)
    stats["dedup"] = len(nouvelles_offres)

    # ── 3. Passe 1 — Filtre mots-clés ────────────────────────────────────────
    logger.info("\n── ÉTAPE 3 : Passe 1 — Filtre mots-clés (gratuit) ──")
    offres_passe1 = keyword_filter.filtrer(nouvelles_offres, criteres)
    stats["passe1"] = len(offres_passe1)

    # ── 4. Passe 2 — Filtre IA ───────────────────────────────────────────────
    logger.info("\n── ÉTAPE 4 : Passe 2 — Filtre IA (Claude Haiku) ──")
    offres_passe2, cout_ia = ai_filter.filtrer(offres_passe1, criteres)
    stats["passe2"] = len(offres_passe2)

    logger.info(
        "\nPipeline : %d collectées → %d après dédup → %d pré-filtre → %d retenues — Coût IA : €%.4f",
        stats["collectees"], stats["dedup"], stats["passe1"], stats["passe2"], cout_ia,
    )

    # Mise à jour des scores IA dans la base
    for offre in offres_passe2:
        h = database.get_hash(offre.get("titre", ""), offre.get("entreprise", ""), offre.get("source", ""))
        database.mettre_a_jour_ia(h, offre.get("resume_ia", ""), offre.get("score_ia", 0))
        offre["hash"] = h

    # ── 5. Matching CV ───────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 5 : Matching CV ──")
    profils_cv = charger_tous_les_cvs()
    moteur = MoteurMatching(profils_cv)
    top_n = criteres.get("seuils", {}).get("top_matchings_par_offre", 3)
    matchings_map = {
        offre.get("hash", ""): moteur.trouver_meilleurs_profils(offre, top_n=top_n)
        for offre in offres_passe2
    }

    # ── 6. Email digest (TOUJOURS envoyé) ────────────────────────────────────
    logger.info("\n── ÉTAPE 6 : Envoi du digest email ──")
    cfg_email = criteres.get("email", {})
    destinataires = cfg_email.get("destinataires", [])

    if not destinataires:
        logger.warning("Aucun destinataire configuré dans criteria.yaml > email > destinataires")
    else:
        date_str = datetime.now().strftime("%d/%m/%Y")
        nb = stats["passe2"]
        if nb == 0:
            objet = f"[ADH Veille] {date_str} — aucune nouvelle offre"
        else:
            objet = f"[ADH Veille] {date_str} — {nb} nouvelle(s) offre(s)"

        if mode_test:
            objet = "[TEST] " + objet

        html = digest.generer_html(
            offres=offres_passe2,
            matchings_map=matchings_map,
            stats=stats,
            cout_ia=cout_ia,
            resultats_sources=resultats_sources,
            mode_test=mode_test,
        )
        succes = digest.envoyer(html, destinataires, objet)

        if succes:
            hashes = [o["hash"] for o in offres_passe2 if o.get("hash")]
            database.marquer_envoyees(hashes)

    logger.info("\n" + "=" * 60)
    logger.info("Agent ADH — terminé. Coût total IA : €%.4f", cout_ia)
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
