"""
Collecteur BOAMP — Bulletin Officiel des Annonces des Marchés Publics.

Utilise l'API REST publique Opendatasoft (v1) :
  https://boamp-datadila.opendatasoft.com/api/records/1.0/search/

Requête : UN SEUL paramètre q, combinaison de trois blocs en ET :
  METIER AND IT AND DATE (parution sur les 30 derniers jours).

Pas de paramètre refine.* : dans l'API v1, plusieurs refine s'additionnent en
ET et produisaient un ensemble vide. Pas de filtre sur dc ni de filtre
géographique : code_departement est le département de l'ACHETEUR, pas le lieu
d'exécution, et code_departement_prestation n'est jamais renseigné. Le tri
géographique est laissé au filtre IA, qui lit l'objet complet.

L'index BOAMP est insensible aux accents : une seule forme par terme suffit.
"""

import logging
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

from .base import BaseCollector

logger = logging.getLogger(__name__)

API_URL = "https://boamp-datadila.opendatasoft.com/api/records/1.0/search/"
SOURCE_BOAMP = "BOAMP"
ROWS_PAR_APPEL = 100
MAX_ANNONCES = 500        # plafond de sécurité par exécution (~5 annonces / semaine en réalité)
FENETRE_JOURS = 30        # dateparution >= aujourd'hui - 30 jours

BLOC_METIER = (
    '("assistance à maîtrise d\'ouvrage" OR AMOA OR "chef de projet" '
    'OR "conduite de projet")'
)
BLOC_IT = (
    '("système d\'information" OR informatique OR numérique OR logiciel '
    'OR applicatif OR "transformation digitale")'
)


def construire_requete(aujourdhui: date | None = None) -> str:
    """q = METIER AND IT AND DATE, la date étant recalculée à chaque exécution."""
    aujourdhui = aujourdhui or date.today()
    depuis = (aujourdhui - timedelta(days=FENETRE_JOURS)).isoformat()
    return f'{BLOC_METIER} AND {BLOC_IT} AND dateparution>="{depuis}"'


def construire_url(q: str, start: int = 0) -> str:
    return (
        f"{API_URL}?dataset=boamp&q={quote(q, safe='')}"
        f"&rows={ROWS_PAR_APPEL}&start={start}"
    )


def _texte(valeur) -> str:
    """Champ Opendatasoft → texte : les listes sont jointes par ", "."""
    if valeur is None:
        return ""
    if isinstance(valeur, list):
        return ", ".join(str(v).strip() for v in valeur if str(v).strip())
    return str(valeur).strip()


def _date_limite_depassee(valeur, maintenant: datetime | None = None) -> bool:
    """True si datelimitereponse est dans le passé ; absent ou illisible → False (conservée)."""
    texte = _texte(valeur)
    if not texte:
        return False
    try:
        limite = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        try:
            limite = datetime.fromisoformat(texte[:10])
        except ValueError:
            return False
    if limite.tzinfo is not None:
        maintenant = maintenant.astimezone(limite.tzinfo) if maintenant else datetime.now(limite.tzinfo)
        return limite < maintenant
    maintenant = (maintenant or datetime.now()).replace(tzinfo=None)
    if len(texte) <= 10:      # date seule : l'annonce reste valable toute la journée
        return limite.date() < maintenant.date()
    return limite < maintenant


class BoampCollector(BaseCollector):
    def collecter(self, criteres: dict) -> list[dict]:
        q = construire_requete()
        records, nhits = self._appeler_api(q)

        offres, ecartees = [], 0
        for record in records:
            fields = record.get("fields", {})
            if _date_limite_depassee(fields.get("datelimitereponse")):
                ecartees += 1
                continue
            offre = self._parser_record(record)
            if offre:
                offres.append(offre)

        logger.info(
            "[BOAMP] nhits=%d, récupérées=%d, écartées (date limite dépassée)=%d, retenues=%d",
            nhits, len(records), ecartees, len(offres),
        )
        return offres

    def _appeler_api(self, q: str) -> tuple[list[dict], int]:
        """Pagination par start (+100) tant que start < nhits, plafonnée à MAX_ANNONCES.

        Erreur HTTP, réseau ou réponse illisible : l'exception remonte, pour que
        la source soit comptée en échec et non « à 0 offre ».
        """
        records: list[dict] = []
        nhits = 0
        start = 0
        while True:
            url = construire_url(q, start)
            logger.info(
                "[BOAMP] Appel : %s?dataset=boamp&q=%s&rows=%d&start=%d",
                API_URL, q, ROWS_PAR_APPEL, start,
            )
            time.sleep(self.delai)
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as e:
                raise RuntimeError(
                    f"[BOAMP] Réponse non-JSON (HTTP {response.status_code}) : {response.text[:200]!r}"
                ) from e
            if not isinstance(data, dict) or "records" not in data:
                raise RuntimeError(f"[BOAMP] Réponse illisible : {str(data)[:200]}")

            nhits = int(data.get("nhits", 0) or 0)
            page = data.get("records") or []
            records.extend(page)
            if start == 0:
                logger.info("[BOAMP] nhits annoncé par l'API : %d", nhits)

            start += ROWS_PAR_APPEL
            if not page or start >= nhits or start >= MAX_ANNONCES:
                break

        if nhits > MAX_ANNONCES:
            logger.warning("[BOAMP] %d annonces annoncées : plafond de %d atteint", nhits, MAX_ANNONCES)
        return records[:MAX_ANNONCES], nhits

    def _parser_record(self, record: dict) -> dict | None:
        """Transforme un enregistrement Opendatasoft en offre normalisée."""
        fields = record.get("fields", {})

        objet = _texte(fields.get("objet"))
        if not objet:
            return None

        id_web = _texte(fields.get("idweb")) or _texte(record.get("recordid"))
        url = _texte(fields.get("url_avis")) or (
            f"https://www.boamp.fr/avis/detail/{id_web}" if id_web else ""
        )

        description_parts = [objet]
        for champ in ("procedure_libelle", "descripteur_libelle", "nature_libelle"):
            valeur = _texte(fields.get(champ))
            if valeur:
                description_parts.append(valeur)
        date_limite = _texte(fields.get("datelimitereponse"))
        if date_limite:
            description_parts.append(f"Date limite de réponse : {date_limite}")

        offre = self.normaliser(
            titre=objet,
            entreprise=_texte(fields.get("nomacheteur")),
            # Département de l'ACHETEUR, tel quel (ex. "94,45"), et non le lieu
            # d'exécution de la prestation.
            lieu=_texte(fields.get("code_departement")),
            type_contrat="Appel d'offres",
            url=url,
            description=" | ".join(description_parts),
            source=SOURCE_BOAMP,
        )
        offre["tjm_min"] = None   # les marchés publics ne publient pas de TJM
        offre["tjm_max"] = None
        date_parution = _texte(fields.get("dateparution"))
        if date_parution:
            offre["date_publication"] = date_parution
        return offre
