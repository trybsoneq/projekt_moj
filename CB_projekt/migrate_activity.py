"""Idempotent migration for flag history and unique challenge solves."""
from sqlalchemy import inspect, text

from database import engine, DATABASE_PATH, Base
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "submissions" not in tables:
        raise RuntimeError(f"Nie udało się utworzyć tabeli submissions w bazie: {DATABASE_PATH}")

    required_columns = {"id", "user_id", "challenge_id", "is_correct", "submitted_at"}
    actual_columns = {
        column["name"] for column in inspector.get_columns("submissions")
    }
    missing = required_columns - actual_columns
    if missing:
        raise RuntimeError(
            "Tabela submissions nie zawiera wymaganych kolumn: "
            + ", ".join(sorted(missing))
        )

    with engine.begin() as connection:
        duplicates = connection.execute(text("""
            SELECT user_id, challenge_id
            FROM solves
            GROUP BY user_id, challenge_id
            HAVING COUNT(*) > 1
            LIMIT 1
        """)).first()
        if duplicates is None:
            connection.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_solves_user_challenge
                ON solves (user_id, challenge_id)
            """))
            print("Unikalność rozwiązania na użytkownika i zadanie: OK")
        else:
            print(
                "UWAGA: wykryto historyczne duplikaty w tabeli solves; "
                "pominięto tworzenie indeksu unikalnego, aby nie usuwać danych."
            )

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Tabela submissions: OK")
    print("Migracja historii prób zakończona.")


if __name__ == "__main__":
    migrate()
