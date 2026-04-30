"""
Collecteur APEC — Association Pour l'Emploi des Cadres.

Stratégie : Playwright headless avec interception réseau.
  APEC est une Angular SPA — le navigateur charge la page et appelle
  une API JSON interne. On intercepte cette réponse directement.
  Pagination : on recharge successivement &page=0, &page=1, ... jusqu'à
  0 résultats ou MAX_PAGES_APEC pages.

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

MAX_PAGES_APEC = 5  # 5 pages × ~15-20 offres = ~75-100 offres max par mot-clé

# URLs de la SPA Angular
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
        try:
            offres = self._scraper_avec_playwright(urls)
        except ImportError:
            logger.error("[APEC] Playwright non installé (pip install playwright + playwright install chromium)")
            return []
        except Exception as e:
            logger.error("[APEC] Erreur Playwright : %s", e)
            return []
        return self._dedupliquer(offres)

    def _parser_api(self, resultats: list) -> list[dict]:
        """Parse les résultats JSON de l'API interne APEC."""
        import re
        from datetime import datetime, timedelta, timezone

        offres = []
        date_limite = datetime.now(timezone.utc) - timedelta(days=21)
        nb_ecartees_date = 0

        CONTRATS_APEC = {
            # Codes typesConvention (paramètre de filtre URL)
            "143684": "CDI",
            "143685": "CDD",
            "143686": "Mission",
            "143687": "Freelance",
            # Codes typeContrat (champ JSON de l'offre)
            "101887": "CDD",
            "101888": "CDI",
        }

        for r in resultats:
            # ── Filtre temporel : offres > 21 jours écartées ─────────────────
            date_str = r.get("datePublication", "")
            if date_str:
                try:
                    date_pub = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if date_pub < date_limite:
                        nb_ecartees_date += 1
                        continue
                except Exception:
                    pass

            # ── Titre — OBLIGATOIRE ───────────────────────────────────────────
            titre = (
                r.get("intitule") or r.get("titre") or r.get("title") or r.get("libelle", "")
            ).strip()
            if not titre:
                continue

            # ── Entreprise — APEC anonymise souvent ──────────────────────────
            entreprise = ""
            soc = (
                r.get("entreprise") or r.get("nomCommercial")
                or r.get("societe") or r.get("employer") or {}
            )
            if isinstance(soc, dict):
                entreprise = soc.get("nom", "") or soc.get("name", "")
            elif isinstance(soc, str):
                entreprise = soc

            # ── Lieu — lieuTexte est la version lisible ("Nanterre - 92") ────
            lieu = r.get("lieuTexte") or r.get("lieu") or r.get("localisation") or r.get("location") or ""
            if isinstance(lieu, dict):
                lieu = lieu.get("libelle", "") or lieu.get("ville", "") or lieu.get("label", "")

            # ── ID complet avec lettre finale (ex: 178503733W) ────────────────
            id_offre = str(r.get("numeroOffre") or r.get("numIdOffre") or r.get("id") or "")
            url = (
                f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{id_offre}"
                if id_offre else ""
            )

            # ── Type de contrat — mapping codes numériques APEC ───────────────
            type_contrat_raw = r.get("typeContrat") or r.get("libelleTypeContrat") or {}
            if isinstance(type_contrat_raw, dict):
                type_contrat = type_contrat_raw.get("libelle", "CDI/CDD")
            else:
                code = str(type_contrat_raw).strip()
                type_contrat = CONTRATS_APEC.get(code)
                if type_contrat is None:
                    if code:
                        if not hasattr(self, "_warned_codes"):
                            self._warned_codes = set()
                        if code not in self._warned_codes:
                            logger.warning("[APEC] Code contrat inconnu : %s", code)
                            self._warned_codes.add(code)
                    type_contrat = code or "CDI/CDD"

            # ── Description — texteOffre contient la vraie description ─────────
            description = (
                r.get("texteOffre") or r.get("texteHtml")
                or r.get("description") or r.get("accroche") or titre
            )
            if isinstance(description, str):
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

        logger.info("[APEC] Filtre temporel : %d offres écartées (>21 jours), %d conservées",
                    nb_ecartees_date, len(offres))
        return offres

    # ── Playwright ────────────────────────────────────────────────────────────

    def _scraper_avec_playwright(self, urls: list) -> list[dict]:
        import re as re_module
        from urllib.parse import unquote
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

            for url_base in urls:
                mots_cles = "?"
                if "motsCles=" in url_base:
                    mots_cles = unquote(url_base.split("motsCles=")[1].split("&")[0])

                offres_url = []
                nb_pages = 0

                for page_num in range(MAX_PAGES_APEC):
                    if re_module.search(r"page=\d+", url_base):
                        url_page = re_module.sub(r"page=\d+", f"page={page_num}", url_base)
                    else:
                        url_page = url_base + f"&page={page_num}"

                    try:
                        nouvelles = self._scraper_page_playwright(page, url_page)
                        logger.info("[APEC] Page %d de '%s' : %d offres récupérées",
                                    page_num, mots_cles, len(nouvelles))

                        if not nouvelles:
                            break

                        offres_url.extend(nouvelles)
                        nb_pages += 1

                        if page_num < MAX_PAGES_APEC - 1:
                            time.sleep(self.delai)

                    except Exception as e:
                        logger.error("[APEC][PW] Erreur page %d de '%s' : %s", page_num, mots_cles, e)
                        break

                logger.info("[APEC] Total '%s' : %d offres sur %d page(s)",
                            mots_cles, len(offres_url), nb_pages)
                offres.extend(offres_url)

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
