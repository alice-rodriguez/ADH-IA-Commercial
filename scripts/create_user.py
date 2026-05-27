"""Bootstrap CLI : créer ou réinitialiser un utilisateur ADH."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth.users import (
    creer_user,
    get_user_par_username,
    reset_password,
)


def main() -> None:
    print("=== Gestion des utilisateurs ADH ===\n")
    username = input("Nom d'utilisateur : ").strip()
    if not username:
        print("Erreur : nom d'utilisateur vide.")
        sys.exit(1)

    existing = get_user_par_username(username)

    if existing:
        print(f"L'utilisateur '{username}' existe déjà (id={existing['id']}).")
        choix = input("Réinitialiser le mot de passe ? (o/N) : ").strip().lower()
        if choix != "o":
            print("Annulé.")
            sys.exit(0)
        password = getpass.getpass("Nouveau mot de passe : ")
        confirm = getpass.getpass("Confirmer le mot de passe : ")
        if password != confirm:
            print("Erreur : les mots de passe ne correspondent pas.")
            sys.exit(1)
        if len(password) < 8:
            print("Erreur : le mot de passe doit contenir au moins 8 caractères.")
            sys.exit(1)
        reset_password(existing["id"], password)
        print(f"Mot de passe de '{username}' réinitialisé.")
    else:
        password = getpass.getpass("Mot de passe : ")
        confirm = getpass.getpass("Confirmer le mot de passe : ")
        if password != confirm:
            print("Erreur : les mots de passe ne correspondent pas.")
            sys.exit(1)
        if len(password) < 8:
            print("Erreur : le mot de passe doit contenir au moins 8 caractères.")
            sys.exit(1)
        user_id = creer_user(username, password)
        print(f"Utilisateur '{username}' créé (id={user_id}).")


if __name__ == "__main__":
    main()
