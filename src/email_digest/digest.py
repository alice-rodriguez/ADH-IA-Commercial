"""
Génération et envoi du digest email quotidien.

Format : email HTML aux couleurs ADH (orange #ff914d, violet #d6a9cf).
Envoi via SMTP Microsoft 365 (inclus dans votre abonnement M365).
"""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Génération du HTML
# ──────────────────────────────────────────────────────────────────────────────

def _badge_type(type_contrat: str) -> str:
    couleurs = {
        "CDI":              "#2d6a4f",
        "CDD":              "#52796f",
        "Freelance":        "#d4a017",
        "Mission":          "#d4a017",
        "Appel d'offres":   "#a06030",
    }
    for cle, couleur in couleurs.items():
        if cle.lower() in type_contrat.lower():
            return f'<span style="background:{couleur};color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">{cle}</span>'
    return f'<span style="background:#888;color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;">{type_contrat}</span>'


def _carte_offre(offre: dict, matchings: list) -> str:
    score = offre.get("score_ia", 0)
    couleur_score = "#2d6a4f" if score >= 80 else "#d4a017" if score >= 60 else "#c0392b"

    lignes_matching = ""
    if matchings:
        lignes_matching = "<br>".join(
            f"<span style='color:#ff914d;font-weight:600;'>→ {m['nom_candidat']}</span> "
            f"<span style='color:#888;font-size:12px;'>({m['score_matching']}% de correspondance)</span>"
            for m in matchings
        )
        lignes_matching = f"""
        <div style="margin-top:10px;padding:8px 12px;background:#fff8f4;border-left:3px solid #ff914d;border-radius:0 6px 6px 0;">
          <div style="font-size:12px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px;">Profils suggérés</div>
          {lignes_matching}
        </div>"""

    return f"""
    <div style="background:#fff;border:1px solid #eee;border-radius:8px;padding:16px 20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div style="flex:1;">
          <div style="margin-bottom:6px;">{_badge_type(offre.get('type_contrat', ''))}</div>
          <h3 style="margin:0 0 4px 0;font-size:16px;color:#1a1a1a;">
            <a href="{offre.get('url', '#')}" style="color:#1a1a1a;text-decoration:none;">{offre.get('titre', '')}</a>
          </h3>
          <div style="color:#555;font-size:13px;">
            {offre.get('entreprise', '') or '—'} &nbsp;·&nbsp; {offre.get('lieu', '') or '—'}
          </div>
        </div>
        <div style="text-align:center;min-width:52px;">
          <div style="background:{couleur_score};color:#fff;border-radius:50%;width:46px;height:46px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;margin:0 auto;">{score}</div>
          <div style="font-size:10px;color:#999;margin-top:2px;">score IA</div>
        </div>
      </div>
      <p style="margin:10px 0 0 0;color:#444;font-size:14px;line-height:1.6;">{offre.get('resume_ia', offre.get('description', ''))[:300]}</p>
      {lignes_matching}
      <div style="margin-top:12px;">
        <a href="{offre.get('url', '#')}" style="color:#ff914d;font-size:13px;text-decoration:none;font-weight:600;">Voir l'offre →</a>
        <span style="color:#ccc;margin:0 8px;">|</span>
        <span style="color:#aaa;font-size:12px;">Source : {offre.get('source', '')}</span>
      </div>
    </div>"""


def _section(titre_section: str, offres_section: list, matchings_map: dict, icone: str) -> str:
    if not offres_section:
        return ""
    cartes = "".join(_carte_offre(o, matchings_map.get(o.get("hash", ""), [])) for o in offres_section)
    return f"""
    <div style="margin-bottom:32px;">
      <h2 style="color:#ff914d;font-size:18px;border-bottom:2px solid #ff914d;padding-bottom:6px;margin-bottom:16px;">
        {icone} {titre_section} <span style="color:#999;font-size:14px;font-weight:400;">({len(offres_section)} offre{'s' if len(offres_section) > 1 else ''})</span>
      </h2>
      {cartes}
    </div>"""


def generer_html(offres: list, matchings_map: dict, stats: dict, cout_ia: float) -> str:
    """
    Génère le HTML complet de l'email digest.

    offres        : liste d'offres retenues (avec score_ia, resume_ia, etc.)
    matchings_map : dict {hash_offre: [{'nom_candidat': ..., 'score_matching': ...}]}
    stats         : {'collectees': N, 'passe1': N, 'passe2': N}
    cout_ia       : coût en € du filtrage IA
    """
    date_str = datetime.now().strftime("%A %d %B %Y").capitalize()

    cdi_cdd     = [o for o in offres if any(t in o.get("type_contrat", "") for t in ["CDI", "CDD"])]
    freelance   = [o for o in offres if any(t in o.get("type_contrat", "") for t in ["Freelance", "Mission"])]
    ao          = [o for o in offres if "offres" in o.get("type_contrat", "").lower() or "appel" in o.get("type_contrat", "").lower()]

    msg_vide = ""
    if not offres:
        msg_vide = """
        <div style="text-align:center;padding:40px;color:#999;background:#fafafa;border-radius:8px;border:1px dashed #ddd;">
          <div style="font-size:40px;margin-bottom:8px;">📭</div>
          <p style="margin:0;font-size:15px;">Aucune nouvelle opportunité correspondant à vos critères aujourd'hui.</p>
        </div>"""

    sections = (
        _section("CDI / CDD", cdi_cdd, matchings_map, "💼")
        + _section("Freelance / Missions", freelance, matchings_map, "🎯")
        + _section("Appels d'offres publics", ao, matchings_map, "🏛️")
        + msg_vide
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

  <!-- RÉSUMÉ CHIFFRÉ -->
  <div style="background:#fff;border-left:1px solid #eee;border-right:1px solid #eee;padding:20px 32px;">
    <div style="display:flex;gap:0;border-radius:8px;overflow:hidden;border:1px solid #eee;">
      <div style="flex:1;text-align:center;padding:14px 8px;background:#fff8f4;border-right:1px solid #eee;">
        <div style="font-size:28px;font-weight:700;color:#ff914d;">{stats.get('collectees', 0)}</div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Collectées</div>
      </div>
      <div style="flex:1;text-align:center;padding:14px 8px;border-right:1px solid #eee;">
        <div style="font-size:28px;font-weight:700;color:#555;">{stats.get('passe1', 0)}</div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Après filtre</div>
      </div>
      <div style="flex:1;text-align:center;padding:14px 8px;background:#f8f4ff;">
        <div style="font-size:28px;font-weight:700;color:#d6a9cf;">{stats.get('passe2', 0)}</div>
        <div style="font-size:11px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">Retenues</div>
      </div>
    </div>
    <div style="text-align:right;margin-top:8px;font-size:11px;color:#ccc;">
      Coût IA aujourd'hui : €{cout_ia:.4f}
    </div>
  </div>

  <!-- CONTENU DES OFFRES -->
  <div style="background:#fff;border:1px solid #eee;border-top:none;border-bottom:none;padding:24px 32px;">
    {sections}
  </div>

  <!-- PIED DE PAGE -->
  <div style="background:#1a1a1a;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center;">
    <div style="font-size:13px;font-weight:700;color:#ff914d;letter-spacing:1px;">ADH Project Management Consulting</div>
    <div style="font-size:12px;color:#666;margin-top:6px;">Digest généré automatiquement par l'agent IA ADH</div>
    <div style="font-size:11px;color:#444;margin-top:4px;">
      Pour modifier les critères, éditez le fichier <code style="color:#d6a9cf;">config/criteria.yaml</code>
    </div>
  </div>

</div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Envoi de l'email via SMTP Microsoft 365
# ──────────────────────────────────────────────────────────────────────────────

def envoyer(html: str, destinataires: list, objet: str) -> bool:
    """
    Envoie l'email via SMTP Microsoft 365.
    Utilise les variables d'environnement EMAIL_EXPEDITEUR et EMAIL_MOT_DE_PASSE.
    """
    expediteur = os.getenv("EMAIL_EXPEDITEUR")
    mot_de_passe = os.getenv("EMAIL_MOT_DE_PASSE")
    serveur_smtp = os.getenv("EMAIL_SERVEUR_SMTP", "smtp.office365.com")
    port_smtp = int(os.getenv("EMAIL_PORT_SMTP", "587"))

    if not expediteur or not mot_de_passe:
        logger.error(
            "Variables EMAIL_EXPEDITEUR ou EMAIL_MOT_DE_PASSE manquantes — email non envoyé"
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = objet
    msg["From"] = expediteur
    msg["To"] = ", ".join(destinataires)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(serveur_smtp, port_smtp, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(expediteur, mot_de_passe)
            server.sendmail(expediteur, destinataires, msg.as_string())
        logger.info("Email envoyé à : %s", ", ".join(destinataires))
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Authentification SMTP échouée. "
            "Vérifiez EMAIL_EXPEDITEUR et EMAIL_MOT_DE_PASSE (mot de passe d'application M365)."
        )
        return False
    except Exception as e:
        logger.error("Erreur envoi email : %s", e)
        return False
