"""
Collecteur APEC — Association Pour l'Emploi des Cadres.

Stratégie en deux temps :
  1. API REST interne (rapide, sans navigateur, prioritaire)
     APEC est une Angular SPA qui appelle un backend JSON.
     On appelle ce backend directement — plus stable que le scraping HTML.
  2. Playwright headless (fallback si l'API change ou retourne 403)

URLs de recherche configurées dans config/sources.yaml > apec > urls.
Elles ciblent : chef de projet / business analyst / MOA
               secteur banque-assurance-finance (101757)
               Île-de-France (711) + full remote
               types de contrat CDI/CDD/Freelance/Mission (143684-143687)
"""

import logging
import time

from .base import BaseCollector

logger = logging.getLogger(__name__)

# API REST interne qu'APEC appelle depuis son frontend Angular
# (observable en inspectant les requêtes réseau du navigateur sur apec.fr)
API_REST_URL = "https://www.apec.fr/cms/webservices/rechercheoffre/paginer"

# URLs de la SPA Angular (fallback Playwright)
URLS_APEC_DEFAULT = [
    "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=chef%20de%20projet&typesConvention=143684&typesConvention=143685&typesConvention=143686&typesConvention=143687&secteursActivite=101757&teletravailFrequence=FULL_REMOTE&lieux=711&page=0",
    "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=business%20analyst&typesConvention=143684&typesConvention=143685&typesConvention=143686&typesConvention=143687&secteursActivite=101757&teletravailFrequence=FULL_REMOTE&lieux=711&page=0",
    "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=moa&typesConvention=143684&typesConvention=143685&typesConvention=143686&typesConvention=143687&secteursActivite=101757&teletravailFrequence=FULL_REMOTE&lieux=711&page=0",
    "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=moa&typesConvention=143684&typesConvention=143685&typesConvention=143686&typesConvention=143687&secteursActivite=101757&teletravailFrequence=FULL_REMOTE&typesTeletravail=20767",
]

# Sélecteurs CSS à essayer dans l'ordre (Playwright fallback HTML)
SELECTEURS_LISTE = [
    "[data-id-offre]",
    "[data-numoffre]",
    "ul.result-list li",
    "li[class*='result']",
    "li[class*='offre']",
    "li[class*='offer']",
    "li[class*='card']",
    "div[class*='card-offre']",
    "div.result-item",
    "article.offer-card",
    "li.offer-item",
    ".results-list li",
    "article",
]
SELECTEURS_TITRE = ["h2 a", "h2", "h3 a", "h3", ".title a", ".title", "a.offer-link"]
SELECTEURS_ENTREPRISE = [".company", ".employer", ".entreprise", ".company-name", "span.company"]
SELECTEURS_LIEU = [".location", ".localisation", ".lieu", "span.location"]


class ApecCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        urls = self.config.get("urls", URLS_APEC_DEFAULT)

        # ── Tentative 1 : API REST interne ───────────────────────────────────
        offres = self._essayer_api_rest(criteres)
        if offres:
            logger.info("[APEC] API REST : %d offres collectées", len(offres))
            return self._dedupliquer(offres)

        logger.info("[APEC] API REST indisponible — bascule sur Playwright")

        # ── Tentative 2 : Playwright headless ────────────────────────────────
        try:
            offres = self._scraper_avec_playwright(urls)
        except ImportError:
            logger.error("[APEC] Playwright non installé (pip install playwright + playwright install chromium)")
            return []
        except Exception as e:
            logger.error("[APEC] Erreur Playwright : %s", e)
            return []

        return self._dedupliquer(offres)

    # ── API REST ──────────────────────────────────────────────────────────────

    def _essayer_api_rest(self, criteres: dict) -> list[dict]:
        """
        Appelle l'API JSON interne d'APEC.
        Paramètres reproduits depuis les URLs de recherche utilisateur.
        """
        headers_api = {
            **self.session.headers,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
            "X-Requested-With": "XMLHttpRequest",
        }

        recherches = [
            {"motsCles": "chef de projet", "secteursActivite": [101757]},
            {"motsCles": "business analyst", "secteursActivite": [101757]},
            {"motsCles": "MOA", "secteursActivite": [101757]},
        ]

        offres = []
        for params_recherche in recherches:
            payload = {
                "motsCles": params_recherche["motsCles"],
                "typesConvention": [143684, 143685, 143686, 143687],
                "secteursActivite": params_recherche["secteursActivite"],
                "lieux": [711],
                "nbResultatsParPage": 20,
                "page": 0,
                "avecNbOffreParDomaineMetier": False,
            }
            try:
                time.sleep(self.delai)
                response = self.session.post(
                    API_REST_URL,
                    json=payload,
                    headers=headers_api,
                    timeout=15,
                )
                if response.status_code != 200:
                    logger.debug(
                        "[APEC] API REST POST : HTTP %d pour '%s'",
                        response.status_code, params_recherche["motsCles"],
                    )
                    return []

                data = response.json()
                resultats = (
                    data.get("resultats", [])
                    or data.get("offres", [])
                    or data.get("results", [])
                    or (data if isinstance(data, list) else [])
                )
                logger.info("[APEC] API REST '%s' : %d résultats", params_recherche["motsCles"], len(resultats))
                offres.extend(self._parser_api(resultats))

            except Exception as e:
                logger.debug("[APEC] API REST erreur pour '%s' : %s", params_recherche["motsCles"], e)
                return []

        return offres

    def _parser_api(self, resultats: list) -> list[dict]:
        """Parse les résultats JSON de l'API interne APEC."""
        offres = []

        # TEMPORAIRE — à retirer une fois confirmé que numIdOffre contient la lettre finale
        if resultats and not getattr(self, "_diag_apec_logged", False):
            import json as _json
            logger.info("[APEC-DIAG] Premier résultat brut : %s", _json.dumps(resultats[0], ensure_ascii=False)[:800])
            self._diag_apec_logged = True  # une seule fois par run

        for r in resultats:
            # L'API peut retourner les champs sous différentes clés selon la version
            titre = (
                r.get("intitule") or r.get("titre") or r.get("title") or r.get("libelle", "")
            ).strip()
            if not titre:
                continue

            entreprise = ""
            soc = r.get("nomCommercial") or r.get("societe") or r.get("employer") or {}
            if isinstance(soc, dict):
                entreprise = soc.get("nom", "") or soc.get("name", "")
            elif isinstance(soc, str):
                entreprise = soc

            lieu = ""
            loc = r.get("lieu") or r.get("localisation") or r.get("location") or {}
            if isinstance(loc, dict):
                lieu = loc.get("libelle", "") or loc.get("ville", "") or loc.get("label", "")
            elif isinstance(loc, str):
                lieu = loc

            id_offre = str(r.get("numIdOffre") or r.get("id") or r.get("offerId") or "")
            url = (
                f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{id_offre}"
                if id_offre else ""
            )

            type_contrat_raw = r.get("typeContrat") or r.get("libelleTypeContrat") or {}
            if isinstance(type_contrat_raw, dict):
                type_contrat = type_contrat_raw.get("libelle", "CDI/CDD")
            else:
                type_contrat = str(type_contrat_raw) or "CDI/CDD"

            description = r.get("texteHtml") or r.get("description") or r.get("accroche") or titre
            if isinstance(description, str):
                import re
                description = re.sub(r"<[^>]+>", " ", description).strip()

            offres.append(
                self.normaliser(
                    titre=titre,
                    entreprise=entreprise,
                    lieu=lieu or "Île-de-France",
                    type_contrat=type_contrat,
                    url=url,
                    description=description[:1500],
                    source=self.nom,
                )
            )
        return offres

    # ── Playwright fallback ───────────────────────────────────────────────────

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
                    logger.info("[APEC][PW] Chargement : %s", url[:80])
                    nouvelles = self._scraper_page_playwright(page, url)
                    offres.extend(nouvelles)
                    logger.info("[APEC][PW] → %d offres", len(nouvelles))
                    time.sleep(self.delai)
                except Exception as e:
                    logger.error("[APEC][PW] Erreur sur %s : %s", url[:80], e)

            browser.close()
        return offres

    def _scraper_page_playwright(self, page, url: str) -> list[dict]:
        """
        Stratégie principale : interception réseau.
        Quand le navigateur charge la page APEC, il appelle une API JSON en coulisses.
        On intercepte cette réponse JSON directement — pas besoin de sélecteurs CSS.
        Fallback : scraping HTML si aucune API n'est capturée.
        """
        import json as json_module

        reponses_api = []

        # Patterns d'URL de l'API APEC (observable en inspectant le réseau dans DevTools)
        PATTERNS_API = [
            "rechercheoffre",
            "rechercheOffre",
            "offre/public",
            "webservices/recherche",
        ]

        def capturer_reponse(response):
            if response.status != 200:
                return
            if not any(p in response.url for p in PATTERNS_API):
                return
            try:
                texte = response.text()
                data = json_module.loads(texte)
                reponses_api.append({"url": response.url, "data": data})
                logger.info("[APEC][PW] API interceptée : %s", response.url[:100])
            except Exception:
                pass

        page.on("response", capturer_reponse)
        try:
            # domcontentloaded est rapide et ne bloque pas sur les traqueurs/pubs
            # qui empêchent networkidle de se déclencher sur APEC (SPA Angular)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.error("[APEC][PW] Erreur chargement : %s", str(e)[:100])
            page.remove_listener("response", capturer_reponse)
            return []

        # Laisser Angular initialiser et appeler son API de recherche (~3-8s)
        page.wait_for_timeout(12000)
        page.remove_listener("response", capturer_reponse)

        # ── Cas 1 : API interceptée → parse JSON direct ───────────────────────
        if reponses_api:
            offres = []
            for item in reponses_api:
                data = item["data"]
                resultats = (
                    data.get("resultats")
                    or data.get("offres")
                    or data.get("results")
                    or (data if isinstance(data, list) else [])
                )
                if resultats:
                    parsed = self._parser_api(resultats)
                    offres.extend(parsed)
                    logger.info(
                        "[APEC][PW] %d offres extraites via interception API (%s)",
                        len(parsed), item["url"][:80],
                    )
            return offres

        # ── Cas 2 : Pas d'API interceptée → scraping HTML avec diagnostic ─────
        logger.info("[APEC][PW] Aucune API interceptée — tentative scraping HTML")

        selecteur_items = None
        for sel in SELECTEURS_LISTE:
            items_trouves = page.query_selector_all(sel)
            if len(items_trouves) >= 2:  # Au moins 2 items pour éviter les faux positifs
                selecteur_items = sel
                logger.info("[APEC][PW] Sélecteur HTML : '%s' (%d items)", sel, len(items_trouves))
                break

        if not selecteur_items:
            # Log de diagnostic pour identifier le problème à distance
            titre_page = page.title()
            # Cherche des indices dans le HTML sur ce qui est rendu
            nb_articles = len(page.query_selector_all("article"))
            nb_li = len(page.query_selector_all("li"))
            nb_div = len(page.query_selector_all("div[class*='offer'], div[class*='result'], div[class*='job']"))
            logger.warning(
                "[APEC][PW] DIAGNOSTIC — Titre: '%s' | articles: %d | li: %d | div[offer/result/job]: %d",
                titre_page, nb_articles, nb_li, nb_div,
            )
            # Log du premier article s'il existe (pour voir son contenu)
            premier_article = page.query_selector("article")
            if premier_article:
                logger.warning("[APEC][PW] Contenu premier article: %s", premier_article.inner_text()[:300])
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
                    lien = f"https://www.apec.fr{lien}"

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
                    titre=titre, entreprise=entreprise,
                    lieu=lieu or "Île-de-France", type_contrat="CDI/CDD",
                    url=lien, description=item.inner_text().strip()[:500],
                    source=self.nom,
                ))
            except Exception as e:
                logger.debug("[APEC][PW] Erreur parsing item HTML : %s", e)

        return offres

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
