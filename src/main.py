"""
Point d'entrée principal de l'agent ADH.

Orchestration du pipeline complet :
  1. Collecte (toutes les sources en parallèle)
  2. Déduplication (base SQLite)
  3. Passe 1 — Filtre mots-clés (gratuit)
  4. Passe 2 — Filtre IA (Claude Haiku)
  5. Matching CV ↔ offres (TF-IDF, gratuit)
  6. Envoi du digest email (M365 SMTP)
"""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Chargement des variables d'environnement depuis .env
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Configuration du logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("adh.agent")

# ──────────────────────────────────────────────────────────────────────────────
# Imports internes
# ──────────────────────────────────────────────────────────────────────────────
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


def charger_config() -> tuple[dict, dict]:
    """Charge les fichiers YAML de configuration."""
    base = Path(__file__).parent.parent / "config"

    with open(base / "criteria.yaml", encoding="utf-8") as f:
        criteres = yaml.safe_load(f)

    with open(base / "sources.yaml", encoding="utf-8") as f:
        sources_cfg = yaml.safe_load(f)

    return criteres, sources_cfg


def construire_collecteurs(sources_cfg: dict) -> list:
    """Instancie les collecteurs actifs selon la config sources.yaml."""
    classes = {
        "boamp":           BoampCollector,
        "apec":            ApecCollector,
        "indeed":          IndeedCollector,
        "welcometothejungle": WTJCollector,
        "freelance_com":   FreelanceComCollector,
    }

    collecteurs = []
    for cle, cfg in sources_cfg.get("sources", {}).items():
        if cfg.get("active", True) and cle in classes:
            collecteurs.append(classes[cle](cfg))
            logger.info("Source activée : %s", cfg.get("nom", cle))

    return collecteurs


def collecter_en_parallele(collecteurs: list, criteres: dict) -> list:
    """Lance tous les collecteurs simultanément pour gagner du temps."""
    toutes_offres = []

    with ThreadPoolExecutor(max_workers=len(collecteurs)) as executor:
        futures = {
            executor.submit(c.collecter, criteres): c.nom
            for c in collecteurs
        }
        for future in as_completed(futures):
            nom_source = futures[future]
            try:
                offres = future.result()
                toutes_offres.extend(offres)
                logger.info("✓ %s : %d offres collectées", nom_source, len(offres))
            except Exception as e:
                logger.error("✗ %s : erreur de collecte — %s", nom_source, e)

    return toutes_offres


def dedupliquer_et_sauvegarder(offres: list, criteres: dict) -> tuple[list, int]:
    """
    Filtre les doublons (déjà vus dans les 7 derniers jours) et sauvegarde les nouvelles.
    Retourne les offres nouvelles + le nombre de doublons écartés.
    """
    fenetre = criteres.get("seuils", {}).get("fenetre_deduplication_jours", 7)
    nouvelles = []
    doublons = 0

    for offre in offres:
        offre["fenetre_deduplication_jours"] = fenetre
        if database.sauvegarder(offre):
            nouvelles.append(offre)
        else:
            doublons += 1

    logger.info("Déduplication : %d nouvelles, %d doublons écartés", len(nouvelles), doublons)
    return nouvelles, doublons


def run():
    logger.info("=" * 60)
    logger.info("Agent ADH — démarrage %s", datetime.now().strftime("%d/%m/%Y %H:%M"))
    logger.info("=" * 60)

    # ── 0. Initialisation ────────────────────────────────────────────────────
    criteres, sources_cfg = charger_config()
    database.initialiser()

    # ── 1. Collecte ──────────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 1 : Collecte des offres ──")
    collecteurs = construire_collecteurs(sources_cfg)
    toutes_offres = collecter_en_parallele(collecteurs, criteres)
    logger.info("Total brut collecté : %d offres", len(toutes_offres))

    stats = {"collectees": len(toutes_offres), "passe1": 0, "passe2": 0}

    if not toutes_offres:
        logger.warning("Aucune offre collectée — vérifiez les sources.")

    # ── 2. Déduplication ─────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 2 : Déduplication ──")
    nouvelles_offres, _ = dedupliquer_et_sauvegarder(toutes_offres, criteres)

    # ── 3. Passe 1 — Filtre mots-clés (gratuit) ──────────────────────────────
    logger.info("\n── ÉTAPE 3 : Passe 1 — Filtre mots-clés (gratuit) ──")
    offres_passe1 = keyword_filter.filtrer(nouvelles_offres, criteres)
    stats["passe1"] = len(offres_passe1)

    # ── 4. Passe 2 — Filtre IA ───────────────────────────────────────────────
    logger.info("\n── ÉTAPE 4 : Passe 2 — Filtre IA (Claude Haiku) ──")
    offres_passe2, cout_ia = ai_filter.filtrer(offres_passe1, criteres)
    stats["passe2"] = len(offres_passe2)

    logger.info(
        "\nPipeline complet : %d collectées → %d après filtre → %d retenues — Coût IA : €%.4f",
        stats["collectees"], stats["passe1"], stats["passe2"], cout_ia,
    )

    # Mise à jour des scores IA dans la base
    for offre in offres_passe2:
        hash_offre = database.get_hash(
            offre.get("titre", ""),
            offre.get("entreprise", ""),
            offre.get("source", ""),
        )
        database.mettre_a_jour_ia(hash_offre, offre.get("resume_ia", ""), offre.get("score_ia", 0))
        offre["hash"] = hash_offre

    # ── 5. Matching CV ───────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 5 : Matching CV ──")
    profils_cv = charger_tous_les_cvs()
    moteur = MoteurMatching(profils_cv)
    top_n = criteres.get("seuils", {}).get("top_matchings_par_offre", 3)

    matchings_map = {}
    for offre in offres_passe2:
        matchings = moteur.trouver_meilleurs_profils(offre, top_n=top_n)
        matchings_map[offre.get("hash", "")] = matchings

    # ── 6. Email digest ──────────────────────────────────────────────────────
    logger.info("\n── ÉTAPE 6 : Envoi du digest email ──")
    cfg_email = criteres.get("email", {})
    destinataires = cfg_email.get("destinataires", [])
    envoyer_si_vide = cfg_email.get("envoyer_si_vide", True)

    if not offres_passe2 and not envoyer_si_vide:
        logger.info("Aucune offre à envoyer et envoyer_si_vide=false — email annulé.")
    elif destinataires:
        date_str = datetime.now().strftime("%d/%m/%Y")
        objet = cfg_email.get("objet", "ADH — Digest Opportunités du {date}").replace("{date}", date_str)
        html = digest.generer_html(offres_passe2, matchings_map, stats, cout_ia)
        succes = digest.envoyer(html, destinataires, objet)

        if succes:
            hashes = [o["hash"] for o in offres_passe2 if o.get("hash")]
            database.marquer_envoyees(hashes)
    else:
        logger.warning("Aucun destinataire configuré dans criteria.yaml > email > destinataires")

    logger.info("\n" + "=" * 60)
    logger.info("Agent ADH — terminé. Coût total IA : €%.4f", cout_ia)
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
