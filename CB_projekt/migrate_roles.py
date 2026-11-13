"""Idempotent migration for user roles.

The same DATABASE_PATH is used by the web application and every migration.
The migration preserves users, challenges, solves and scores.
"""
from sqlalchemy import inspect, text

from database import DATABASE_PATH, engine, Base
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        raise RuntimeError(
            f"Nie znaleziono tabeli users w bazie: {DATABASE_PATH}"
        )

    user_columns = {column["name"] for column in inspector.get_columns("users")}

    with engine.begin() as connection:
        if "role" not in user_columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                )
            )
        connection.execute(
            text(
                "UPDATE users SET role = 'admin' "
                "WHERE username = 'admin' AND role = 'user'"
            )
        )
        connection.execute(
            text(
                "UPDATE users SET role = 'user' "
                "WHERE role IS NULL OR role = ''"
            )
        )

    migrated_columns = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    if "role" not in migrated_columns:
        raise RuntimeError(
            f"Migracja nie dodała kolumny users.role w bazie: {DATABASE_PATH}"
        )

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Kolumna users.role: OK")
    print("Migracja ról zakończona. Dane użytkowników i wyniki zostały zachowane.")


if __name__ == "__main__":
    migrate()
