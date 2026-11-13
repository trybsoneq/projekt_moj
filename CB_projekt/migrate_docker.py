"""Idempotent migration for per-user Docker challenge instances."""
from sqlalchemy import inspect, text

from database import engine, Base
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("challenges")}
    with engine.begin() as connection:
        if "docker_template" not in columns:
            connection.execute(text("ALTER TABLE challenges ADD COLUMN docker_template VARCHAR(64)"))
        connection.execute(text("""
            UPDATE challenges
            SET docker_template = 'web_sqli', external_url = NULL
            WHERE title = 'Podatna wyszukiwarka'
              AND (docker_template IS NULL OR docker_template = '')
        """))
    print("Migracja Docker zakończona. Dotychczasowe dane zostały zachowane.")


if __name__ == "__main__":
    migrate()
