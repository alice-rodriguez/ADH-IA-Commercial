"""
CORRECTIF-12 — Test HORS RÉSEAU du collecteur BOAMP.

Aucun appel HTTP : la session du collecteur est remplacée par un faux client
qui renvoie un échantillon JSON figé, construit à partir des champs réels de
l'API Opendatasoft (objet, url_avis, dateparution, nomacheteur,
code_departement, procedure_libelle, descripteur_libelle, nature_libelle,
datelimitereponse).

  1. URL complète que le collecteur produirait aujourd'hui (q en clair + encodée)
  2. Parsing de l'échantillon via collecter() : offres normalisées + journal
  3. Pagination (start += 100) et plafond de 500 annonces
  4. Erreurs : HTTP 500 et réponse non-JSON doivent LEVER (source en échec)
  5. Pré-filtre : les offres BOAMP doivent être EXEMPTÉES (filtrer(), lecture seule)
  6. Prompt IA : clause BOAMP présente pour BOAMP, absente pour les autres

Usage (depuis la racine du dépôt) : python scripts/test_boamp.py
"""

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import yaml

for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors import boamp  # noqa: E402

logging.basicConfig(level=logging.INFO, format="    [log] %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])

AUJ = date.today()
FUTUR = (AUJ + timedelta(days=20)).isoformat() + "T12:00:00+01:00"
PASSE = (AUJ - timedelta(days=5)).isoformat() + "T12:00:00+01:00"

ECHANTILLON = [
    {"recordid": "r1", "fields": {
        "idweb": "25-150001",
        "objet": "Assistance à maîtrise d'ouvrage pour la refonte du système d'information financier",
        "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:25-150001",
        "dateparution": (AUJ - timedelta(days=3)).isoformat(),
        "nomacheteur": "Caisse des Dépôts et Consignations",
        "code_departement": "75",
        "procedure_libelle": "Procédure adaptée",
        "descripteur_libelle": ["Assistance à maîtrise d'ouvrage", "Informatique (prestations de services)"],
        "nature_libelle": "Avis de marché",
        "datelimitereponse": FUTUR,
    }},
    {"recordid": "r2", "fields": {
        "idweb": "25-150002",
        "objet": "AMOA conduite du changement - déploiement d'un logiciel RH",
        "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:25-150002",
        "dateparution": (AUJ - timedelta(days=25)).isoformat(),
        "nomacheteur": "Département du Val-de-Marne",
        "code_departement": "94,45",
        "procedure_libelle": "Appel d'offres ouvert",
        "descripteur_libelle": "Conseil en systèmes informatiques",
        "nature_libelle": "Avis de marché",
        "datelimitereponse": PASSE,          # close : doit être ÉCARTÉE
    }},
    {"recordid": "r3", "fields": {
        "idweb": "25-150003",
        "objet": "Chef de projet numérique - transformation digitale des services aux usagers",
        "dateparution": (AUJ - timedelta(days=1)).isoformat(),
        "nomacheteur": "Ministère de l'Intérieur",
        "code_departement": "974",
        "procedure_libelle": "Procédure adaptée",
        "nature_libelle": "Avis de marché",
        # pas de url_avis (repli sur idweb) ni de datelimitereponse (conservée)
    }},
    {"recordid": "r4", "fields": {
        "idweb": "25-150004",
        "objet": "Conduite de projet applicatif - mise en place d'un portail",
        "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:25-150004",
        "dateparution": (AUJ - timedelta(days=8)).isoformat(),
        "nomacheteur": "Commune de Montreuil",
        "code_departement": ["93"],
        "procedure_libelle": "Procédure adaptée",
        "descripteur_libelle": "Services informatiques",
        "nature_libelle": "Avis de marché",
        "datelimitereponse": "date illisible",   # illisible : conservée
    }},
]


class FausseReponse:
    def __init__(self, status=200, data=None, texte=None):
        self.status_code = status
        self._data = data
        self.text = texte if texte is not None else json.dumps(data or {})

    def json(self):
        if self._data is None:
            raise ValueError("pas du JSON")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error", response=self)


def collecteur(faux_get):
    c = boamp.BoampCollector({"nom": "BOAMP", "delai_secondes": 0})
    c.session.get = faux_get            # AUCUN appel réseau
    return c


def titre(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def main():
    titre("1. URL produite aujourd'hui")
    q = boamp.construire_requete()
    print(f"  q en clair :\n    {q}")
    print(f"  URL complète (page 1) :\n    {boamp.construire_url(q, 0)}")
    print(f"  Paramètres : {sorted(parse_qs(urlparse(boamp.construire_url(q)).query, keep_blank_values=True))}")
    assert "refine" not in boamp.construire_url(q) and "dc=" not in boamp.construire_url(q)

    titre("2. Parsing de l'échantillon via collecter()")
    appels = []

    def get_echantillon(url, timeout=None):
        appels.append(url)
        return FausseReponse(data={"nhits": len(ECHANTILLON), "records": ECHANTILLON})

    offres = collecteur(get_echantillon).collecter({})
    print(f"\n  Appels HTTP simulés : {len(appels)} ; offres retenues : {len(offres)}")
    for o in offres:
        print("  " + "-" * 96)
        for k, v in o.items():
            print(f"    {k:<17}: {v!r}")

    titre("3. Pagination et plafond")
    for nhits in (230, 900):
        starts = []

        def get_pagine(url, timeout=None, nhits=nhits):
            start = int(parse_qs(urlparse(url).query)["start"][0])
            starts.append(start)
            n = max(0, min(boamp.ROWS_PAR_APPEL, nhits - start))
            recs = [{"recordid": f"p{start + i}", "fields": {"objet": f"AMOA SI {start + i}",
                     "datelimitereponse": FUTUR}} for i in range(n)]
            return FausseReponse(data={"nhits": nhits, "records": recs})

        logging.disable(logging.INFO)
        res = collecteur(get_pagine).collecter({})
        logging.disable(logging.NOTSET)
        print(f"  nhits={nhits:<4} -> start appelés {starts} ; offres retenues {len(res)}")

    titre("4. Erreurs : la source doit être comptée en ÉCHEC (exception levée)")
    for lib, rep in [("HTTP 500", FausseReponse(status=500, texte="boom")),
                     ("réponse non-JSON", FausseReponse(status=200, texte="<html>maintenance</html>"))]:
        try:
            logging.disable(logging.INFO)
            collecteur(lambda url, timeout=None, rep=rep: rep).collecter({})
            print(f"  {lib:<18} -> AUCUNE exception (ÉCHEC du test)")
        except Exception as e:
            print(f"  {lib:<18} -> {type(e).__name__} levée : {str(e)[:90]}")
        finally:
            logging.disable(logging.NOTSET)

    titre("5. Pré-filtre : les offres BOAMP doivent être EXEMPTÉES (filtrer())")
    from src.filters.keyword_filter import evaluer, filtrer
    with open(ROOT / "config" / "criteria.yaml", encoding="utf-8") as f:
        criteres = yaml.safe_load(f)
    retenues = filtrer([dict(o) for o in offres], criteres)
    print(f"  filtrer() : {len(offres)} offres BOAMP en entrée -> {len(retenues)} transmises au filtre IA")
    print("  Pour information, verdict de evaluer() si BOAMP n'était pas exempté :")
    for o in offres:
        ok, score, raison = evaluer(dict(o), criteres)
        print(f"    {'ACCEPTÉ' if ok else 'REJET  '} (score={score}) {raison:<30} | {o['titre'][:70]}")

    titre("6. Prompt IA : clause BOAMP")
    from src.filters import ai_filter

    class FauxClient:
        def __init__(self):
            self.prompt, self.messages = None, self

        def create(self, **kw):
            self.prompt = kw["messages"][0]["content"]
            raise RuntimeError("pas d'appel API")

    logging.disable(logging.CRITICAL)
    prompts = {}
    for source in ("BOAMP", "Free-Work"):
        c = FauxClient()
        ai_filter.analyser_offre(dict(offres[0], source=source), criteres, c)
        prompts[source] = c.prompt
    logging.disable(logging.NOTSET)
    print(f"  Clause présente pour BOAMP     : {'MARCHÉ PUBLIC (BOAMP)' in prompts['BOAMP']}")
    print(f"  Clause présente pour Free-Work : {'MARCHÉ PUBLIC (BOAMP)' in prompts['Free-Work']}")
    debut = prompts["BOAMP"].index("- Niveau requis")
    fin = prompts["BOAMP"].index("Titre :")
    print("  Extrait du prompt BOAMP :")
    for ligne in prompts["BOAMP"][debut:fin].rstrip().splitlines():
        print(f"    | {ligne}")


if __name__ == "__main__":
    main()
