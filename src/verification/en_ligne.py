"""
FANTÔMES-01 — Vérifier que les offres sont encore en ligne.

Règles de détection mesurées sur les vrais sites le 20/11/2026 :

  Free-Work : ne renvoie jamais d'erreur ; on suit les redirections et on lit l'URL finale.
    - URL finale avec "expire=1", ou sans "/job-mission/"  → HORS LIGNE
      (ex. .../job-mission/chef-de-projet-sap-pm → .../tech-it/jobs?expire=1&query=...)
    - URL finale avec "/job-mission/"                       → EN LIGNE
  HelloWork : statut HTTP explicite, sur la même URL (redirections non suivies).
    - 200 → EN LIGNE ; 410 ou 404 → HORS LIGNE (ex. /fr-fr/emplois/85107847.html → 410)
  Tout autre cas (délai dépassé, 403, 500, erreur réseau, redirection inattendue) → INCONNU.
  Une offre INCONNUE n'est JAMAIS masquée : dans le doute, on la montre.

Exclusions : BOAMP (son url_avis pointe vers une page de recherche qui répond toujours ;
sa date limite de réponse joue ce rôle) et « Manuelle » (saisies par Alice).
Aucune offre n'est jamais supprimée : seuls statut_en_ligne et date_verification changent.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

from src.storage.database import (
    EN_LIGNE, HORS_LIGNE, INCONNU, _connexion, migrer_offres_en_ligne, sql_offre_active,
)

logger = logging.getLogger(__name__)

SOURCES_VERIFIEES = ("Free-Work", "HelloWork")
TIMEOUT_SECONDES = 20
# Plafond d'offres interrogées par run : borne le temps du pipeline et la charge
# imposée aux sites (au délai de politesse de 2 s, 80 offres ≈ 3 minutes).
MAX_VERIFICATIONS_PAR_RUN = 80
# Une offre vérifiée il y a moins de 12 h n'est pas réinterrogée.
INTERVALLE_MIN_HEURES = 12
DELAI_POLITESSE_DEFAUT = 2   # secondes, si la source n'en déclare pas dans config/sources.yaml

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


# ── Classement (fonctions pures, testées hors réseau) ───────────────────────

def classer_free_work(statut_http: int, url_finale: str) -> str:
    if statut_http != 200:
        return INCONNU
    if "expire=1" in url_finale or "/job-mission/" not in url_finale:
        return HORS_LIGNE
    return EN_LIGNE


def classer_hellowork(statut_http: int) -> str:
    if statut_http == 200:
        return EN_LIGNE
    if statut_http in (404, 410):
        return HORS_LIGNE
    return INCONNU


def verifier_url(session, source: str, url: str, timeout: int = TIMEOUT_SECONDES) -> tuple[str, str]:
    """(statut, détail) pour une URL d'offre. Aucune exception ne remonte : erreur → INCONNU."""
    try:
        if source == "Free-Work":
            r = session.get(url, timeout=timeout, allow_redirects=True)
            return classer_free_work(r.status_code, r.url), f"HTTP {r.status_code} → {r.url}"
        if source == "HelloWork":
            r = session.get(url, timeout=timeout, allow_redirects=False)
            return classer_hellowork(r.status_code), f"HTTP {r.status_code}"
        return INCONNU, f"source non vérifiable : {source}"
    except requests.exceptions.Timeout:
        return INCONNU, f"délai dépassé ({timeout} s)"
    except requests.exceptions.RequestException as e:
        return INCONNU, f"erreur réseau : {type(e).__name__}"
    except Exception as e:  # jamais bloquant pour le pipeline
        return INCONNU, f"erreur : {type(e).__name__}"


# ── Sélection des offres à risque ────────────────────────────────────────────

def delais_politesse() -> dict[str, float]:
    """{nom de source: delai_secondes} lus dans config/sources.yaml (même délai que les collecteurs)."""
    chemin = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"
    try:
        sources = yaml.safe_load(chemin.read_text(encoding="utf-8")).get("sources", {})
        return {cfg.get("nom"): cfg.get("delai_secondes", DELAI_POLITESSE_DEFAUT) for cfg in sources.values()}
    except Exception:
        return {}


def _table_existe(conn, nom: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,)).fetchone() is not None


def selectionner_a_verifier(debut_run: str, score_min: int, limite: int,
                            maintenant: datetime | None = None) -> list[dict]:
    """Offres à risque, les jamais vérifiées d'abord puis les plus anciennement vérifiées :
      - sources Free-Work et HelloWork ;
      - retenues par l'IA (score_ia >= score_min) ou portant un positionnement manuel ;
      - PAS revues par les collecteurs pendant ce run (date_derniere_vue < debut_run) ;
      - vérifiées il y a plus de INTERVALLE_MIN_HEURES heures (ou jamais) ;
      - encore affichables (ni périmées ni déjà hors ligne : inutile de les réinterroger).
    """
    migrer_offres_en_ligne()
    m = maintenant or datetime.now()
    verif_max = (m - timedelta(hours=INTERVALLE_MIN_HEURES)).isoformat()
    clause, params = sql_offre_active("o")
    marques = ", ".join("?" for _ in SOURCES_VERIFIEES)
    with _connexion() as conn:
        manuel = ("OR EXISTS (SELECT 1 FROM matchings mt WHERE mt.offre_id = o.id "
                  "AND COALESCE(mt.ajout_manuel, 0) = 1)") if _table_existe(conn, "matchings") else ""
        rows = conn.execute(
            f"""
            SELECT o.id, o.source, o.url, o.titre FROM offres o
            WHERE o.source IN ({marques})
              AND o.url LIKE 'http%'
              AND (o.score_ia >= ? {manuel})
              AND COALESCE(o.date_derniere_vue, o.date_collecte) < ?
              AND (o.date_verification IS NULL OR o.date_verification < ?)
              AND {clause}
            ORDER BY o.date_verification IS NOT NULL, o.date_verification,
                     COALESCE(o.date_derniere_vue, o.date_collecte)
            LIMIT ?
            """,
            [*SOURCES_VERIFIEES, score_min, debut_run, verif_max, *params, limite],
        ).fetchall()
    return [dict(r) for r in rows]


def rehabiliter_revues(debut_run: str) -> int:
    """Une offre marquée hors ligne mais retrouvée dans les listes pendant ce run est vivante."""
    migrer_offres_en_ligne()
    with _connexion() as conn:
        cur = conn.execute(
            "UPDATE offres SET statut_en_ligne = ?, date_verification = ? "
            "WHERE statut_en_ligne = ? AND date_derniere_vue >= ?",
            (EN_LIGNE, datetime.now().isoformat(), HORS_LIGNE, debut_run),
        )
        return cur.rowcount


# ── Exécution ────────────────────────────────────────────────────────────────

def verifier_offres(debut_run: str, score_min: int = 60, limite: int = MAX_VERIFICATIONS_PAR_RUN,
                    session=None, ecrire: bool = True, dormir=None) -> dict:
    """Vérifie les offres à risque et enregistre leur statut. Retourne le bilan.

    debut_run : horodatage (isoformat) du début du run ; les offres revues depuis ne sont pas interrogées.
    ecrire=False : simulation (affichage seul, aucune écriture en base).
    """
    bilan = {"verifiees": 0, EN_LIGNE: 0, HORS_LIGNE: 0, INCONNU: 0,
             "rehabilitees": 0, "plafond": limite, "plafond_atteint": False, "details": []}
    if ecrire:
        bilan["rehabilitees"] = rehabiliter_revues(debut_run)

    # limite + 1 pour savoir si le plafond a tronqué la liste
    offres = selectionner_a_verifier(debut_run, score_min, limite + 1)
    bilan["plafond_atteint"] = len(offres) > limite
    offres = offres[:limite]
    if not offres:
        logger.info("Vérification en ligne : aucune offre à vérifier")
        return bilan

    delais = delais_politesse()
    dormir = dormir or time.sleep
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)

    for offre in offres:
        dormir(delais.get(offre["source"], DELAI_POLITESSE_DEFAUT))
        statut, detail = verifier_url(session, offre["source"], offre["url"])
        bilan["verifiees"] += 1
        bilan[statut] += 1
        bilan["details"].append({**offre, "statut": statut, "detail": detail})
        logger.info("[EN-LIGNE] %s | %s | %s | %s", offre["source"], statut, (offre["titre"] or "")[:60], detail)
        if ecrire:
            with _connexion() as conn:
                conn.execute("UPDATE offres SET statut_en_ligne = ?, date_verification = ? WHERE id = ?",
                             (statut, datetime.now().isoformat(), offre["id"]))

    logger.info(
        "Vérification en ligne : %d vérifiée(s) — %d en ligne, %d hors ligne, %d inconnue(s)%s%s",
        bilan["verifiees"], bilan[EN_LIGNE], bilan[HORS_LIGNE], bilan[INCONNU],
        f" — plafond de {limite} atteint, le reste au prochain run" if bilan["plafond_atteint"] else "",
        f" — {bilan['rehabilitees']} offre(s) hors ligne retrouvée(s) dans les listes" if bilan["rehabilitees"] else "",
    )
    return bilan
