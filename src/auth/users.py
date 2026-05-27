"""CRUD utilisateurs."""
from src.auth.passwords import hash_password
from src.storage.database import _connexion


def creer_user(username: str, password: str) -> int:
    """Hash le mdp et insère le user. Raise si username déjà pris."""
    password_hash = hash_password(password)
    with _connexion() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
    return cur.lastrowid


def get_user_par_username(username: str) -> dict | None:
    with _connexion() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def get_user_par_id(user_id: int) -> dict | None:
    with _connexion() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    with _connexion() as conn:
        rows = conn.execute(
            "SELECT id, username, date_creation FROM users ORDER BY date_creation ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def supprimer_user(user_id: int) -> None:
    with _connexion() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def reset_password(user_id: int, new_password: str) -> None:
    new_hash = hash_password(new_password)
    with _connexion() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id),
        )
