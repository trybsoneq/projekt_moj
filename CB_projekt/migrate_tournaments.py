"""Idempotent schema migration for teams and tournaments."""
from sqlalchemy import inspect

from database import engine, DATABASE_PATH, Base
import models  # noqa: F401 - registers tournament models on Base.metadata


def migrate() -> None:
    # Standalone execution must also upgrade all preceding stages first.
    from migrate_achievements import migrate as migrate_achievements

    migrate_achievements()
    Base.metadata.create_all(bind=engine)

    required = {
        "teams": {"id", "name", "description", "invite_code", "owner_user_id", "created_at"},
        "team_members": {"id", "team_id", "user_id", "role", "joined_at"},
        "team_invitations": {"id", "team_id", "invited_user_id", "invited_by_user_id", "status", "created_at"},
        "tournaments": {
            "id", "title", "description", "competition_type", "starts_at",
            "ends_at", "status", "max_participants", "created_by_user_id", "created_at",
        },
        "tournament_challenges": {"id", "tournament_id", "challenge_id", "points"},
        "tournament_participants": {"id", "tournament_id", "user_id", "joined_at"},
        "tournament_team_participants": {"id", "tournament_id", "team_id", "joined_at"},
        "tournament_solves": {
            "id", "tournament_id", "challenge_id", "user_id", "team_id",
            "solver_user_id", "points", "solved_at",
        },
    }
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    for table, expected_columns in required.items():
        if table not in actual_tables:
            raise RuntimeError(f"Nie udało się utworzyć tabeli {table} w bazie: {DATABASE_PATH}")
        actual_columns = {column["name"] for column in inspector.get_columns(table)}
        missing = expected_columns - actual_columns
        if missing:
            raise RuntimeError(
                f"Tabela {table} nie zawiera kolumn: " + ", ".join(sorted(missing))
            )

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Tabele teams / team_members / team_invitations: OK")
    print("Tabele tournaments / participants / tournament_solves: OK")
    print("Migracja turniejów zakończona.")


if __name__ == "__main__":
    migrate()
