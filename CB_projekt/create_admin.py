"""Tworzy lub promuje konto administratora.

Hasło jest wprowadzane interaktywnie i nie jest zapisywane w repozytorium.
"""
import getpass

from passlib.context import CryptContext
from database import SessionLocal
import models
from migrate_roles import migrate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> None:
    migrate()
    username = input("Nazwa administratora: ").strip()
    if not username:
        raise SystemExit("Nazwa użytkownika nie może być pusta.")

    password = getpass.getpass("Hasło (min. 12 znaków): ")
    confirm = getpass.getpass("Powtórz hasło: ")
    if len(password) < 12:
        raise SystemExit("Hasło musi mieć co najmniej 12 znaków.")
    if len(password.encode("utf-8")) > 72:
        raise SystemExit("Hasło jest zbyt długie (maksymalnie 72 bajty w UTF-8).")
    if not 3 <= len(username) <= 32 or not all(
        character.isalnum() or character in "._-" for character in username
    ):
        raise SystemExit("Nazwa administratora musi mieć 3–32 znaki: litery, cyfry, . _ -.")

    if password != confirm:
        raise SystemExit("Hasła nie są identyczne.")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user is None:
            user = models.User(
                username=username,
                password_hash=pwd_context.hash(password),
                role="admin",
            )
            db.add(user)
        else:
            user.password_hash = pwd_context.hash(password)
            user.role = "admin"
        db.commit()
        print(f"Konto {username!r} ma teraz rolę administratora.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
