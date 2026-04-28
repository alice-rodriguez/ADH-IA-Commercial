"""
Génération et envoi du digest email quotidien.

Format  : email HTML aux couleurs ADH (orange #ff914d, violet #d6a9cf).
Envoi   : Microsoft Graph API (OAuth2 client credentials) — compatible 2FA M365.
Prérequis Azure AD : application avec permission Mail.Send (Application) + admin consent.
"""

import logging
import os
from datetime import datetime

import msal
import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers HTML
# ──────────────────────────────────────────────────────────────────────────────

def _badge_type(type_contrat: str) -> str:
    couleurs = {
        "CDI":            "#2d6a4f",
        "CDD":            "#52796f",
        "Freelance":      "#d4a017",
        "Mission":        "#d4a017",
        "Appel d'offres": "#a06030",
    }
    for cle, couleur in couleurs.items():
        if cle.lower() in type_contrat.lower():
            return (
                f'<span style="background:{couleur};color:#fff;padding:2px 8px;'
                f'border-radius:12px;font-size:11px;font-weight:600;">{cle}</span>'
            )
    return (
        f'<span style="background:#888;color:#fff;padding:2px 8px;'
        f'border-radius:12px;font-size:11px;">{type_contrat}</span>'
    )


def _section_statut_sources(resultats_sources: list) -> str:
    """Bloc 'Statut des sources' affiché en haut de l'email, toujours présent."""
    lignes = ""
    for r in resultats_sources:
        if r.get("statut") == "ok":
            icone = "✓"
            couleur = "#2d6a4f"
            detail = f"{r.get('count', 0)} offre{'s' if r.get('count', 0) != 1 else ''} collectée{'s' if r.get('count', 0) != 1 else ''}"
        else:
            icone = "✗"
            couleur = "#c0392b"
            detail = r.get("erreur", "erreur inconnue")

        lignes += (
            f'<div style="padding:5px 0;border-bottom:1px solid #f0f0f0;display:flex;'
            f'align-items:baseline;gap:8px;">'
            f'<span style="color:{couleur};font-weight:700;min-width:16px;">{icone}</span>'
            f'<span style="font-weight:600;color:#333;min-width:180px;">{r.get("nom", "")}</span>'
            f'<span style="color:#666;font-size:13px;">{detail}</span>'
            f"</div>"
        )

    return f"""
    <div style="background:#fff;border:1px solid #eee;border-top:none;border-bottom:none;padding:16px 32px 0 32px;">
      <h2 style="color:#555;font-size:14px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 10px 0;">
        Statut des sources
      </h2>
      <div style="font-size:14px;line-height:1.8;">{lignes}</div>
    </div>"""


def _bloc_pipeline(stats: dict, cout_ia: float) -> str:
    """Résumé chiffré du pipeline, toujours affiché."""
    return f"""
    <div style="background:#fff;border-left:1px solid #eee;border-right:1px solid #eee;padding:16px 32px;">
      <h2 style="color:#555;font-size:14px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 10px 0;">
        Résumé du pipeline
      </h2>
      <div style="display:flex;gap:0;border-radius:8px;overflow:hidden;border:1px solid #eee;">
        <div style="flex:1;text-align:center;padding:12px 6px;background:#fff8f4;border-right:1px solid #eee;">
          <div style="font-size:26px;font-weight:700;color:#ff914d;">{stats.get('collectees', 0)}</div>
          <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Collectées</div>
        </div>
        <div style="flex:1;text-align:center;padding:12px 6px;border-right:1px solid #eee;">
          <div style="font-size:26px;font-weight:700;color:#888;">{stats.get('dedup', 0)}</div>
          <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Après dédup.</div>
        </div>
        <div style="flex:1;text-align:center;padding:12px 6px;border-right:1px solid #eee;">
          <div style="font-size:26px;font-weight:700;color:#555;">{stats.get('passe1', 0)}</div>
          <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Pré-filtre</div>
        </div>
        <div style="flex:1;text-align:center;padding:12px 6px;background:#f8f4ff;">
          <div style="font-size:26px;font-weight:700;color:#d6a9cf;">{stats.get('passe2', 0)}</div>
          <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Retenues IA</div>
        </div>
      </div>
      <div style="text-align:right;margin-top:6px;font-size:11px;color:#ccc;">
        Coût IA aujourd'hui : €{cout_ia:.4f}
      </div>
    </div>"""


def _carte_offre(offre: dict, matchings: list) -> str:
    score = offre.get("score_ia", 0)
    couleur_score = "#2d6a4f" if score >= 80 else "#d4a017" if score >= 60 else "#c0392b"

    lignes_matching = ""
    if matchings:
        contenu = "<br>".join(
            f"<span style='color:#ff914d;font-weight:600;'>→ {m['nom_candidat']}</span> "
            f"<span style='color:#888;font-size:12px;'>({m['score_matching']}% de correspondance)</span>"
            for m in matchings
        )
        lignes_matching = (
            '<div style="margin-top:10px;padding:8px 12px;background:#fff8f4;'
            'border-left:3px solid #ff914d;border-radius:0 6px 6px 0;">'
            '<div style="font-size:12px;color:#888;margin-bottom:4px;'
            'text-transform:uppercase;letter-spacing:0.5px;">Profils suggérés</div>'
            f"{contenu}</div>"
        )

    return (
        '<div style="background:#fff;border:1px solid #eee;border-radius:8px;'
        'padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
        f'<div style="flex:1;">'
        f'<div style="margin-bottom:6px;">{_badge_type(offre.get("type_contrat", ""))}</div>'
        f'<h3 style="margin:0 0 4px 0;font-size:16px;color:#1a1a1a;">'
        f'<a href="{offre.get("url", "#")}" style="color:#1a1a1a;text-decoration:none;">'
        f'{offre.get("titre", "")}</a></h3>'
        f'<div style="color:#555;font-size:13px;">'
        f'{offre.get("entreprise", "") or "—"} &nbsp;·&nbsp; {offre.get("lieu", "") or "—"}'
        f"</div></div>"
        f'<div style="text-align:center;min-width:52px;">'
        f'<div style="background:{couleur_score};color:#fff;border-radius:50%;width:46px;height:46px;'
        f'display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;margin:0 auto;">'
        f"{score}</div>"
        f'<div style="font-size:10px;color:#999;margin-top:2px;">score IA</div>'
        f"</div></div>"
        f'<p style="margin:10px 0 0 0;color:#444;font-size:14px;line-height:1.6;">'
        f'{offre.get("resume_ia", offre.get("description", ""))[:300]}</p>'
        f"{lignes_matching}"
        f'<div style="margin-top:12px;">'
        f'<a href="{offre.get("url", "#")}" style="color:#ff914d;font-size:13px;text-decoration:none;font-weight:600;">Voir l\'offre →</a>'
        f'<span style="color:#ccc;margin:0 8px;">|</span>'
        f'<span style="color:#aaa;font-size:12px;">Source : {offre.get("source", "")}</span>'
        f"</div></div>"
    )


def _section_offres(titre_section: str, offres_section: list, matchings_map: dict, icone: str) -> str:
    if not offres_section:
        return ""
    cartes = "".join(
        _carte_offre(o, matchings_map.get(o.get("hash", ""), []))
        for o in offres_section
    )
    nb = len(offres_section)
    return (
        f'<div style="margin-bottom:32px;">'
        f'<h2 style="color:#ff914d;font-size:18px;border-bottom:2px solid #ff914d;'
        f'padding-bottom:6px;margin-bottom:16px;">'
        f'{icone} {titre_section} <span style="color:#999;font-size:14px;font-weight:400;">'
        f'({nb} offre{"s" if nb > 1 else ""})</span></h2>'
        f"{cartes}</div>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Génération HTML principale
# ──────────────────────────────────────────────────────────────────────────────

def generer_html(
    offres: list,
    matchings_map: dict,
    stats: dict,
    cout_ia: float,
    resultats_sources: list,
    mode_test: bool = False,
) -> str:
    """
    Génère le HTML complet de l'email digest.

    offres            : offres retenues après filtrage IA
    matchings_map     : {hash_offre: [{nom_candidat, score_matching}]}
    stats             : {collectees, dedup, passe1, passe2}
    cout_ia           : coût total en € du filtrage IA
    resultats_sources : [{nom, statut, count | erreur}]
    mode_test         : affiche la bannière jaune si True
    """
    date_str = datetime.now().strftime("%A %d %B %Y").capitalize()

    banniere_test = ""
    if mode_test:
        banniere_test = (
            '<div style="background:#fff3cd;border:2px solid #ffc107;border-radius:8px;'
            'padding:12px 20px;margin-bottom:16px;text-align:center;font-weight:700;color:#856404;">'
            "⚠️ MODE TEST ACTIVÉ — offres fictives injectées — ceci n'est pas un vrai digest"
            "</div>"
        )

    cdi_cdd   = [o for o in offres if any(t in o.get("type_contrat", "") for t in ["CDI", "CDD"])]
    freelance = [o for o in offres if any(t in o.get("type_contrat", "") for t in ["Freelance", "Mission"])]
    ao        = [o for o in offres if "offres" in o.get("type_contrat", "").lower() or "appel" in o.get("type_contrat", "").lower()]

    contenu_offres = (
        _section_offres("CDI / CDD", cdi_cdd, matchings_map, "💼")
        + _section_offres("Freelance / Missions", freelance, matchings_map, "🎯")
        + _section_offres("Appels d'offres publics", ao, matchings_map, "🏛️")
    )

    if not offres:
        contenu_offres = (
            '<div style="text-align:center;padding:40px;color:#999;background:#fafafa;'
            'border-radius:8px;border:1px dashed #ddd;">'
            '<div style="font-size:40px;margin-bottom:8px;">📭</div>'
            "<p style=\"margin:0;font-size:15px;\">Aucune nouvelle offre pertinente détectée aujourd'hui.</p>"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADH — Digest {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:680px;margin:0 auto;padding:24px 16px;">

  <!-- EN-TÊTE -->
  <div style="background:linear-gradient(135deg,#ff914d 0%,#d6a9cf 100%);border-radius:12px 12px 0 0;padding:28px 32px;text-align:center;">
    <div style="font-size:32px;font-weight:900;color:#fff;letter-spacing:-1px;">ADH</div>
    <div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:2px;">Project Management Consulting</div>
    <div style="color:#fff;font-size:20px;font-weight:600;margin-top:12px;">Digest Opportunités</div>
    <div style="color:rgba(255,255,255,0.8);font-size:14px;margin-top:4px;">{date_str}</div>
  </div>

  <!-- STATUT DES SOURCES -->
  {_section_statut_sources(resultats_sources)}

  <!-- RÉSUMÉ PIPELINE -->
  {_bloc_pipeline(stats, cout_ia)}

  <!-- BANNIÈRE TEST + OFFRES -->
  <div style="background:#fff;border:1px solid #eee;border-top:none;border-bottom:none;padding:24px 32px;">
    {banniere_test}
    {contenu_offres}
  </div>

  <!-- PIED DE PAGE -->
  <div style="background:#1a1a1a;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center;">
    <div style="font-size:13px;font-weight:700;color:#ff914d;letter-spacing:1px;">ADH Project Management Consulting</div>
    <div style="font-size:12px;color:#666;margin-top:6px;">Digest généré automatiquement par l'agent IA ADH</div>
    <div style="font-size:11px;color:#444;margin-top:4px;">
      Pour modifier les critères, éditez <code style="color:#d6a9cf;">config/criteria.yaml</code>
    </div>
  </div>

</div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Envoi via Microsoft Graph API (OAuth2 client credentials)
# ──────────────────────────────────────────────────────────────────────────────

def _obtenir_token() -> str:
    """
    Obtient un access token Azure AD via client credentials flow.
    Lève une exception explicite si l'acquisition échoue.
    """
    tenant_id     = os.getenv("AZURE_TENANT_ID")
    client_id     = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError(
            "Variables manquantes : AZURE_TENANT_ID, AZURE_CLIENT_ID ou AZURE_CLIENT_SECRET. "
            "Vérifiez votre fichier .env ou les secrets GitHub."
        )

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" in result:
        return result["access_token"]

    raise RuntimeError(
        f"Échec acquisition token Azure AD — "
        f"error={result.get('error')} — "
        f"description={result.get('error_description', 'aucun détail')}"
    )


def envoyer(html: str, destinataires: list, objet: str) -> bool:
    """
    Envoie l'email via Microsoft Graph API.
    Compatible avec les comptes M365 protégés par 2FA (pas besoin de mot de passe d'app).

    Étape 1 : acquisition du token Azure AD
    Étape 2 : appel POST Graph API /sendMail
    """
    expediteur = os.getenv("EMAIL_EXPEDITEUR")
    if not expediteur:
        logger.error("EMAIL_EXPEDITEUR manquant — email non envoyé")
        return False

    # Étape 1 — Token
    try:
        token = _obtenir_token()
        logger.info("Étape 1/2 — Token Azure AD : OK")
    except Exception as e:
        logger.error("Étape 1/2 — Token Azure AD : ÉCHEC — %s", e)
        return False

    # Étape 2 — Envoi via Graph API
    payload = {
        "message": {
            "subject": objet,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [
                {"emailAddress": {"address": d}} for d in destinataires
            ],
        },
        "saveToSentItems": True,
    }
    url = f"https://graph.microsoft.com/v1.0/users/{expediteur}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 202:
            logger.info("Étape 2/2 — Email envoyé via Graph API à : %s", ", ".join(destinataires))
            return True

        # Codes d'erreur explicites
        messages = {
            401: "Token invalide ou expiré — vérifiez AZURE_CLIENT_SECRET",
            403: "Permission refusée — vérifiez que Mail.Send est accordé avec admin consent",
            404: f"Boîte introuvable pour {expediteur} — vérifiez EMAIL_EXPEDITEUR",
            429: "Rate limit atteint — réessayez dans quelques minutes",
        }
        msg = messages.get(
            response.status_code,
            f"Réponse inattendue : {response.text[:300]}",
        )
        logger.error(
            "Étape 2/2 — Graph API : ÉCHEC %d — %s",
            response.status_code, msg,
        )
        return False

    except requests.exceptions.Timeout:
        logger.error("Étape 2/2 — Graph API : timeout (30s) — réseau lent ou Graph indisponible")
        return False
    except Exception as e:
        logger.error("Étape 2/2 — Graph API : exception inattendue — %s", e)
        return False
