"""Gestion des sessions utilisateur (token uuid4, durée 7 jours)."""
import uuid
from datetime import datetime, timedelta

from src.storage.database import _connexion

SESSION_DAYS = 7


def creer_session(user_id: int) -> tuple[str, str]:
    """Crée une session et retourne (token, date_expiration ISO)."""
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=SESSION_DAYS)
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

    with _connexion() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, date_expiration) VALUES (?, ?, ?)",
            (token, user_id, expires_str),
        )

    return token, expires_str


def valider_session(token: str) -> dict | None:
    """Retourne {user_id, username} si le token est valide, sinon None."""
    with _connexion() as conn:
        row = conn.execute(
            """
            SELECT s.user_id, u.username
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.date_expiration > datetime('now')
            """,
            (token,),
        ).fetchone()

    if row is None:
        return None
    return {"user_id": row["user_id"], "username": row["username"]}


def supprimer_session(token: str) -> None:
    with _connexion() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def nettoyer_sessions_expirees() -> int:
    """Supprime les sessions expirées. Retourne le nombre de lignes supprimées."""
    with _connexion() as conn:
        cur = conn.execute(
            "DELETE FROM sessions WHERE date_expiration <= datetime('now')"
        )
    return cur.rowcount
