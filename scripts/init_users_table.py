"""Initialise les tables users et sessions en BDD (Session G).

Idempotent : CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
"""
import sys
sys.path.insert(0, '.')
from src.storage.database import _connexion

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    date_creation  TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token            TEXT PRIMARY KEY,
    user_id          INTEGER NOT NULL,
    date_creation    TIMESTAMP DEFAULT (datetime('now')),
    date_expiration  TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_expiration
    ON sessions(date_expiration);
"""


def main():
    with _connexion() as conn:
        conn.executescript(SCHEMA)
    print("[OK] Tables users et sessions créées (ou déjà existantes)")


if __name__ == "__main__":
    main()
