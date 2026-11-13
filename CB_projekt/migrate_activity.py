"""Idempotent migration that creates the flag submission history table."""
from sqlalchemy import inspect

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

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Tabela submissions: OK")
    print("Migracja historii prób zakończona.")


if __name__ == "__main__":
    migrate()
