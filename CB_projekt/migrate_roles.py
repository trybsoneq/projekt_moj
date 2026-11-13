"""Jednorazowa, bezpieczna migracja schematu do obsługi ról.

Uruchom: python migrate_roles.py
Nie usuwa użytkowników, zadań ani wyników.
"""
from sqlalchemy import inspect, text

from database import engine, Base
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    with engine.begin() as connection:
        if "role" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
            )
        connection.execute(
            text("UPDATE users SET role = 'admin' WHERE username = 'admin' AND role = 'user'")
        )
        connection.execute(
            text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")
        )
    print("Migracja ról zakończona. Dane użytkowników i wyniki zostały zachowane.")


if __name__ == "__main__":
    migrate()
