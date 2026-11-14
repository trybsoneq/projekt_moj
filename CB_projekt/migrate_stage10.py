"""Stage 10: idempotent SQLite indexes for common leaderboard and activity queries."""
from sqlalchemy import inspect, text

from database import engine, DATABASE_PATH


INDEXES = {
    "ix_users_score_username": "CREATE INDEX IF NOT EXISTS ix_users_score_username ON users (score DESC, username ASC)",
    "ix_solves_timestamp_user": "CREATE INDEX IF NOT EXISTS ix_solves_timestamp_user ON solves (timestamp, user_id)",
    "ix_submissions_challenge_time": "CREATE INDEX IF NOT EXISTS ix_submissions_challenge_time ON submissions (challenge_id, submitted_at)",
    "ix_tournaments_status_dates": "CREATE INDEX IF NOT EXISTS ix_tournaments_status_dates ON tournaments (status, starts_at, ends_at)",
    "ix_tournament_solves_event_time": "CREATE INDEX IF NOT EXISTS ix_tournament_solves_event_time ON tournament_solves (tournament_id, solved_at)",
    "ix_team_members_team_role": "CREATE INDEX IF NOT EXISTS ix_team_members_team_role ON team_members (team_id, role)",
    "ix_challenge_instances_created": "CREATE INDEX IF NOT EXISTS ix_challenge_instances_created ON challenge_instances (created_at DESC)",
}


def migrate() -> None:
    from migrate_notifications import migrate as migrate_notifications

    migrate_notifications()
    existing_tables = set(inspect(engine).get_table_names())
    required_tables = {
        "users", "solves", "submissions", "tournaments",
        "tournament_solves", "team_members", "challenge_instances",
    }
    missing = required_tables - existing_tables
    if missing:
        raise RuntimeError(
            "Nie można utworzyć indeksów etapu 10; brakuje tabel: "
            + ", ".join(sorted(missing))
        )

    with engine.begin() as connection:
        for statement in INDEXES.values():
            connection.execute(text(statement))

    index_inspector = inspect(engine)
    for table in required_tables:
        index_names = {item["name"] for item in index_inspector.get_indexes(table)}
        expected = {
            name for name in INDEXES
            if f" ON {table} " in INDEXES[name]
        }
        missing_indexes = expected - index_names
        if missing_indexes:
            raise RuntimeError(
                f"Nie udało się utworzyć indeksów dla tabeli {table}: "
                + ", ".join(sorted(missing_indexes))
            )

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print(f"Indeksy etapu 10: {len(INDEXES)} — OK")


if __name__ == "__main__":
    migrate()
