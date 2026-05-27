"""Hashing et vérification de mots de passe via bcrypt (direct, rounds=12)."""
import bcrypt

_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_ROUNDS)).decode()


def verify_password(password: str, hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), hash.encode())
