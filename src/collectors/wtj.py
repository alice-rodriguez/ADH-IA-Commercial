"""
Collecteur Welcome to the Jungle (WTJ).

Stratégie en deux temps :
  1. Playwright headless + interception des réponses Algolia (prioritaire)
     WTJ est un site Next.js qui appelle Algolia en coulisses pour la recherche.
     On intercepte les réponses JSON Algolia directement — pas de sélecteurs CSS.
  2. Scraping HTML Playwright (fallback si Algolia non capturée)

URLs de recherche configurées dans config/sources.yaml > welcometothejungle > urls.
Elles ciblent : chef de projet / business analyst / MOA
               secteur banque-finance-assurance
               Île-de-France + remote
"""

import logging
import time

from .base import BaseCollector

logger = logging.getLogger(__name__)

# Patterns d'URL Algolia observés dans les requêtes réseau de WTJ
PATTERNS_ALGOLIA = [
    "algolia.net",
    "algolianet.com",
    "algolia.io",
]

# Sélecteurs CSS de fallback (scraping HTML)
SELECTEURS_LISTE = [
    "li[data-testid]",
    "ul li",
    "article",
    "div[class*='job']",
    "div[class*='result']",
]
SELECTEURS_TITRE = [
    "h2 a", "h2", "h3 a", "h3",
    "[data-testid='job-title']",
    ".title", "a[href*='/jobs/']",
]
SELECTEURS_ENTREPRISE = [
    "[data-testid='company-name']",
    ".company", ".employer",
    "span[class*='company']",
]
SELECTEURS_LIEU = [
    "[data-testid='location']",
    ".location", ".lieu",
    "span[class*='location']",
    "span[class*='city']",
]

CONTRACT_MAP = {
    "full_time": "CDI",
    "part_time": "CDI partiel",
    "temporary": "CDD",
    "freelance": "Freelance",
    "internship": "Stage",
    "apprenticeship": "Alternance",
    "vie": "VIE",
}

URLS_WTJ_DEFAULT = [
    "https://www.welcometothejungle.com/fr/jobs?query=chef%20de%20projet&refinementList%5Boffices.country_code%5D%5B%5D=FR&refinementList%5Bcontract_type%5D%5B%5D=full_time&refinementList%5Bcontract_type%5D%5B%5D=temporary&refinementList%5Bcontract_type%5D%5B%5D=freelance",
    "https://www.welcometothejungle.com/fr/jobs?query=business%20analyst&refinementList%5Boffices.country_code%5D%5B%5D=FR&refinementList%5Bcontract_type%5D%5B%5D=full_time&refinementList%5Bcontract_type%5D%5B%5D=temporary&refinementList%5Bcontract_type%5D%5B%5D=freelance",
    "https://www.welcometothejungle.com/fr/jobs?query=MOA%20banque&refinementList%5Boffices.country_code%5D%5B%5D=FR",
]


class WTJCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        urls = self.config.get("urls", URLS_WTJ_DEFAULT)

        try:
            offres = self._scraper_avec_playwright(urls)
        except ImportError:
            logger.error("[WTJ] Playwright non installé (pip install playwright + playwright install chromium)")
            return []
        except Exception as e:
            logger.error("[WTJ] Erreur Playwright : %s", e)
            return []

        offres = self._dedupliquer(offres)
        logger.info("[WTJ] Total : %d offres uniques", len(offres))
        return offres

    # ── Playwright ────────────────────────────────────────────────────────────

    def _scraper_avec_playwright(self, urls: list) -> list[dict]:
        from playwright.sync_api import sync_playwright

        offres = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
            )
            page = context.new_page()

            for url in urls:
                try:
                    logger.info("[WTJ][PW] Chargement : %s", url[:80])
                    nouvelles = self._scraper_page_playwright(page, url)
                    offres.extend(nouvelles)
                    logger.info("[WTJ][PW] → %d offres", len(nouvelles))
                    time.sleep(self.delai)
                except Exception as e:
                    logger.error("[WTJ][PW] Erreur sur %s : %s", url[:80], e)

            browser.close()
        return offres

    def _scraper_page_playwright(self, page, url: str) -> list[dict]:
        """
        Stratégie principale : interception des réponses Algolia.
        WTJ appelle Algolia pour ses recherches — on intercepte le JSON directement.
        Fallback : scraping HTML si aucune réponse Algolia capturée.
        """
        import json as json_module

        reponses_algolia = []

        def capturer_reponse(response):
            if response.status != 200:
                return
            if not any(p in response.url for p in PATTERNS_ALGOLIA):
                return
            try:
                texte = response.text()
                data = json_module.loads(texte)
                # Algolia retourne soit {"hits": [...]} soit {"results": [{"hits": [...]}]}
                hits = self._extraire_hits(data)
                if hits:
                    reponses_algolia.append({"url": response.url, "hits": hits})
                    logger.info("[WTJ][PW] Algolia interceptée : %d hits (%s)", len(hits), response.url[:80])
            except Exception:
                pass

        page.on("response", capturer_reponse)
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.remove_listener("response", capturer_reponse)

        # ── Cas 1 : Algolia interceptée → parse JSON direct ───────────────────
        if reponses_algolia:
            offres = []
            for item in reponses_algolia:
                parsed = self._parser_hits(item["hits"])
                offres.extend(parsed)
                logger.info("[WTJ][PW] %d offres extraites via Algolia (%s)", len(parsed), item["url"][:80])
            return offres

        # ── Cas 2 : Pas d'Algolia → scraping HTML ────────────────────────────
        logger.info("[WTJ][PW] Aucune Algolia interceptée — tentative scraping HTML")

        selecteur_items = None
        for sel in SELECTEURS_LISTE:
            items_trouves = page.query_selector_all(sel)
            if len(items_trouves) >= 2:
                selecteur_items = sel
                logger.info("[WTJ][PW] Sélecteur HTML : '%s' (%d items)", sel, len(items_trouves))
                break

        if not selecteur_items:
            titre_page = page.title()
            nb_articles = len(page.query_selector_all("article"))
            nb_li = len(page.query_selector_all("li"))
            logger.warning(
                "[WTJ][PW] DIAGNOSTIC — Titre: '%s' | articles: %d | li: %d",
                titre_page, nb_articles, nb_li,
            )
            return []

        offres = []
        for item in page.query_selector_all(selecteur_items)[:20]:
            try:
                titre, lien = "", ""
                for sel in SELECTEURS_TITRE:
                    el = item.query_selector(sel)
                    if el and el.inner_text().strip():
                        titre = el.inner_text().strip()
                        lien = el.get_attribute("href") or ""
                        break
                if not titre:
                    continue
                if lien and not lien.startswith("http"):
                    lien = f"https://www.welcometothejungle.com{lien}"

                entreprise = next(
                    (item.query_selector(s).inner_text().strip()
                     for s in SELECTEURS_ENTREPRISE
                     if item.query_selector(s) and item.query_selector(s).inner_text().strip()),
                    "",
                )
                lieu = next(
                    (item.query_selector(s).inner_text().strip()
                     for s in SELECTEURS_LIEU
                     if item.query_selector(s) and item.query_selector(s).inner_text().strip()),
                    "",
                )
                offres.append(self.normaliser(
                    titre=titre,
                    entreprise=entreprise,
                    lieu=lieu or "Île-de-France",
                    type_contrat="CDI/CDD",
                    url=lien,
                    description=item.inner_text().strip()[:500],
                    source=self.nom,
                ))
            except Exception as e:
                logger.debug("[WTJ][PW] Erreur parsing item HTML : %s", e)

        return offres

    # ── Parsing Algolia ───────────────────────────────────────────────────────

    @staticmethod
    def _extraire_hits(data: dict | list) -> list:
        """Extrait les hits depuis une réponse Algolia (plusieurs formats possibles)."""
        if isinstance(data, list):
            # Multi-query : liste de résultats
            hits = []
            for result in data:
                hits.extend(result.get("hits", []))
            return hits
        if isinstance(data, dict):
            # Réponse simple
            if "hits" in data:
                return data["hits"]
            # Multi-query encapsulé
            if "results" in data:
                hits = []
                for result in data["results"]:
                    hits.extend(result.get("hits", []))
                return hits
        return []

    def _parser_hits(self, hits: list) -> list[dict]:
        """Parse les hits Algolia de WTJ."""
        offres = []
        for hit in hits:
            try:
                titre = (hit.get("name") or hit.get("title") or "").strip()
                if not titre:
                    continue

                org = hit.get("organization") or hit.get("company") or {}
                entreprise = ""
                if isinstance(org, dict):
                    entreprise = org.get("name", "")
                elif isinstance(org, str):
                    entreprise = org

                lieu = self._extraire_lieu_hit(hit)

                slug = hit.get("slug") or hit.get("objectID", "")
                org_slug = ""
                if isinstance(org, dict):
                    org_slug = org.get("slug", "")
                if org_slug and slug:
                    url = f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}"
                elif slug:
                    url = f"https://www.welcometothejungle.com/fr/jobs/{slug}"
                else:
                    url = "https://www.welcometothejungle.com/fr/jobs"

                contrat_raw = hit.get("contract_type") or hit.get("contractType") or ""
                if isinstance(contrat_raw, dict):
                    contrat_raw = contrat_raw.get("key", contrat_raw.get("name", ""))
                type_contrat = CONTRACT_MAP.get(str(contrat_raw).lower(), contrat_raw or "CDI")

                description = (
                    hit.get("description_plain")
                    or hit.get("description")
                    or hit.get("summary")
                    or titre
                )
                if isinstance(description, str):
                    description = description[:1500]

                offres.append(
                    self.normaliser(
                        titre=titre,
                        entreprise=entreprise,
                        lieu=lieu,
                        type_contrat=type_contrat,
                        url=url,
                        description=description,
                        source=self.nom,
                    )
                )
            except Exception as e:
                logger.debug("[WTJ] Erreur parsing hit : %s", e)

        return offres

    @staticmethod
    def _extraire_lieu_hit(hit: dict) -> str:
        offices = hit.get("offices") or hit.get("locations") or []
        if offices and isinstance(offices, list):
            office = offices[0]
            if isinstance(office, dict):
                city = office.get("city") or office.get("name", "")
                state = office.get("state", "")
                if city:
                    return f"{city}, {state}".strip(", ") if state else city
        remote = hit.get("remote") or hit.get("telework_enabled")
        if remote:
            return "Remote"
        return "Île-de-France"

    @staticmethod
    def _dedupliquer(offres: list) -> list:
        vus = set()
        uniques = []
        for o in offres:
            cle = (o["titre"].lower().strip(), o.get("entreprise", "").lower().strip())
            if cle not in vus:
                vus.add(cle)
                uniques.append(o)
        return uniques
