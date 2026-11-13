"""Idempotent migration for per-user Docker challenge instances."""
from sqlalchemy import inspect, text

from database import engine, Base
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    challenge_columns = {column["name"] for column in inspector.get_columns("challenges")}
    instance_columns = {column["name"] for column in inspector.get_columns("challenge_instances")}

    with engine.begin() as connection:
        if "docker_template" not in challenge_columns:
            connection.execute(text("ALTER TABLE challenges ADD COLUMN docker_template VARCHAR(64)"))
        if "proxy_container_id" not in instance_columns:
            connection.execute(text("ALTER TABLE challenge_instances ADD COLUMN proxy_container_id VARCHAR(128)"))
        if "ingress_network_id" not in instance_columns:
            connection.execute(text("ALTER TABLE challenge_instances ADD COLUMN ingress_network_id VARCHAR(128)"))
        connection.execute(text("""
            UPDATE challenges
            SET docker_template = 'web_sqli', external_url = NULL
            WHERE title = 'Podatna wyszukiwarka'
              AND (docker_template IS NULL OR docker_template = '')
        """))
    print("Migracja Docker zakończona. Dotychczasowe dane zostały zachowane.")


if __name__ == "__main__":
    migrate()
