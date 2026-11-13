"""Idempotent migration for three-level challenge hints.

Existing Challenge.hint values are preserved as a free first-level hint.
"""
from sqlalchemy import inspect

from database import engine, DATABASE_PATH, Base, SessionLocal
import models


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    required = {
        "challenge_hints": {"id", "challenge_id", "level", "content", "penalty_points", "is_active"},
        "hint_unlocks": {
            "id", "user_id", "hint_id", "unlocked_at",
            "points_deducted", "hint_content_snapshot",
        },
    }

    for table, columns in required.items():
        if table not in inspector.get_table_names():
            raise RuntimeError(f"Nie udało się utworzyć tabeli {table} w bazie: {DATABASE_PATH}")
        actual = {column["name"] for column in inspector.get_columns(table)}
        missing = columns - actual
        if missing:
            raise RuntimeError(
                f"Tabela {table} nie zawiera wymaganych kolumn: {', '.join(sorted(missing))}"
            )

    db = SessionLocal()
    migrated = 0
    try:
        challenges = (
            db.query(models.Challenge)
            .filter(models.Challenge.hint.isnot(None))
            .all()
        )
        for challenge in challenges:
            legacy_text = (challenge.hint or "").strip()
            if not legacy_text:
                continue
            existing = (
                db.query(models.ChallengeHint)
                .filter(
                    models.ChallengeHint.challenge_id == challenge.id,
                    models.ChallengeHint.level == 1,
                )
                .first()
            )
            if existing is None:
                db.add(models.ChallengeHint(
                    challenge_id=challenge.id,
                    level=1,
                    content=legacy_text,
                    penalty_points=0,
                    is_active=True,
                ))
                migrated += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Tabele challenge_hints i hint_unlocks: OK")
    print(f"Przeniesiono starych wskazówek do poziomu 1: {migrated}")
    print("Migracja podpowiedzi zakończona.")


def migrate_prerequisites() -> None:
    """Bring older databases through the earlier stages before querying ORM models.

    SQLAlchemy create_all() creates missing tables but does not add columns to
    existing SQLite tables. In particular, stage 2 adds challenges.docker_template.
    Running this script directly must therefore apply the earlier idempotent
    migrations before it loads Challenge objects.
    """
    from migrate_roles import migrate as migrate_roles
    from migrate_docker import migrate as migrate_docker
    from migrate_activity import migrate as migrate_activity

    migrate_roles()
    migrate_docker()
    migrate_activity()


if __name__ == "__main__":
    migrate_prerequisites()
    migrate()
