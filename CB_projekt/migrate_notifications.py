"""Idempotent migration for in-app notifications and announcements."""
from sqlalchemy import inspect

from database import engine, DATABASE_PATH, Base
import models  # noqa: F401 - registers all earlier and notification models


def migrate() -> None:
    from migrate_tournaments import migrate as migrate_tournaments

    migrate_tournaments()
    Base.metadata.create_all(bind=engine)

    required = {
        "notifications": {
            "id", "user_id", "category", "title", "body", "target_url",
            "is_read", "created_at", "dedupe_key", "announcement_id",
        },
        "notification_preferences": {
            "id", "user_id", "team_enabled", "tournament_enabled",
            "achievement_enabled", "announcement_enabled", "updated_at",
        },
        "announcements": {
            "id", "title", "body", "created_by_user_id", "created_at",
            "is_active", "sent_at",
        },
        "notification_dispatches": {"id", "event_key", "dispatched_at"},
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, expected in required.items():
        if table not in existing_tables:
            raise RuntimeError(f"Nie udało się utworzyć tabeli {table} w bazie: {DATABASE_PATH}")
        columns = {column["name"] for column in inspector.get_columns(table)}
        missing = expected - columns
        if missing:
            raise RuntimeError(
                f"Tabela {table} nie zawiera wymaganych kolumn: "
                + ", ".join(sorted(missing))
            )

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Tabele notifications / notification_preferences: OK")
    print("Tabele announcements / notification_dispatches: OK")
    print("Migracja powiadomień zakończona.")


if __name__ == "__main__":
    migrate()
