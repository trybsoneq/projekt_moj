"""Idempotent migration for XP, streak tracking and achievement badges."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import inspect, text, func

from database import engine, DATABASE_PATH, Base, SessionLocal
import models
from achievement_service import ACHIEVEMENT_DEFINITIONS, longest_consecutive_days


def migrate_prerequisites() -> None:
    """Ensure all schema fields used by the current ORM exist before ORM queries."""
    from migrate_roles import migrate as migrate_roles
    from migrate_docker import migrate as migrate_docker
    from migrate_activity import migrate as migrate_activity
    from migrate_hints import migrate as migrate_hints

    migrate_roles()
    migrate_docker()
    migrate_activity()
    migrate_hints()


def _ensure_user_columns() -> bool:
    """Add XP/streak fields to existing SQLite users table; return whether XP was new."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)

    columns = {column["name"] for column in inspector.get_columns("users")}
    xp_was_missing = "xp" not in columns
    definitions = {
        "xp": "INTEGER NOT NULL DEFAULT 0",
        "current_streak": "INTEGER NOT NULL DEFAULT 0",
        "longest_streak": "INTEGER NOT NULL DEFAULT 0",
        "last_solve_date": "DATE",
    }
    with engine.begin() as connection:
        for name, sql_type in definitions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
    return xp_was_missing


def _seed_achievements(db) -> dict[str, models.Achievement]:
    result = {}
    for definition in ACHIEVEMENT_DEFINITIONS:
        achievement = (
            db.query(models.Achievement)
            .filter(models.Achievement.code == definition["code"])
            .first()
        )
        if achievement is None:
            achievement = models.Achievement(**definition, is_active=True)
            db.add(achievement)
        else:
            for key, value in definition.items():
                setattr(achievement, key, value)
            achievement.is_active = True
        result[definition["code"]] = achievement
    db.flush()
    return result


def _ensure_award(
    db,
    user: models.User,
    achievements: dict[str, models.Achievement],
    code: str,
    *,
    challenge_id: int | None = None,
    context_key: str = "global",
    event_key: str | None = None,
) -> None:
    achievement = achievements[code]
    existing = (
        db.query(models.UserAchievement)
        .filter(
            models.UserAchievement.user_id == user.id,
            models.UserAchievement.achievement_id == achievement.id,
            models.UserAchievement.context_key == context_key,
        )
        .first()
    )
    if existing:
        return
    if event_key:
        event_exists = (
            db.query(models.UserAchievement.id)
            .filter(models.UserAchievement.event_key == event_key)
            .first()
        )
        if event_exists:
            return
    db.add(models.UserAchievement(
        user_id=user.id,
        achievement_id=achievement.id,
        challenge_id=challenge_id,
        context_key=context_key,
        event_key=event_key,
        xp_awarded=achievement.xp_reward,
        awarded_at=datetime.utcnow(),
    ))
    db.flush()


def _backfill_user_progress(db, achievements: dict[str, models.Achievement]) -> None:
    """Reconstruct badges and streaks from existing Solve rows, safely on reruns."""
    all_solves = (
        db.query(models.Solve)
        .order_by(models.Solve.timestamp.asc(), models.Solve.id.asc())
        .all()
    )
    first_solver_by_challenge: dict[int, models.Solve] = {}
    for solve in all_solves:
        first_solver_by_challenge.setdefault(solve.challenge_id, solve)

    challenges = {
        challenge.id: challenge
        for challenge in db.query(models.Challenge).all()
    }
    solves_by_user: dict[int, list[models.Solve]] = {}
    for solve in all_solves:
        solves_by_user.setdefault(solve.user_id, []).append(solve)

    today_utc = datetime.utcnow().date()
    for user in db.query(models.User).all():
        user_solves = solves_by_user.get(user.id, [])
        solved_count = len(user_solves)
        solve_dates = [
            solve.timestamp.date()
            for solve in user_solves
            if solve.timestamp is not None
        ]
        unique_dates = sorted(set(solve_dates))
        longest = longest_consecutive_days(unique_dates)
        last_date = unique_dates[-1] if unique_dates else None

        current = 0
        if last_date and last_date >= today_utc - timedelta(days=1):
            current = 1
            cursor = last_date
            for previous in reversed(unique_dates[:-1]):
                if previous == cursor - timedelta(days=1):
                    current += 1
                    cursor = previous
                else:
                    break

        user.last_solve_date = last_date
        user.current_streak = current
        user.longest_streak = longest

        if solved_count >= 1:
            _ensure_award(db, user, achievements, "first_solve")
        if solved_count >= 5:
            _ensure_award(db, user, achievements, "solver_5")
        if solved_count >= 10:
            _ensure_award(db, user, achievements, "solver_10")
        if longest >= 3:
            _ensure_award(db, user, achievements, "streak_3")
        if longest >= 7:
            _ensure_award(db, user, achievements, "streak_7")

        categories = {
            challenges[solve.challenge_id].category
            for solve in user_solves
            if solve.challenge_id in challenges
        }
        if len(categories) >= 3:
            _ensure_award(db, user, achievements, "category_explorer_3")

        total_challenges = len(challenges)
        unique_solved = len({solve.challenge_id for solve in user_solves})
        if total_challenges and unique_solved >= total_challenges:
            _ensure_award(db, user, achievements, "completionist")

        for challenge_id, first_solve in first_solver_by_challenge.items():
            if first_solve.user_id == user.id:
                _ensure_award(
                    db,
                    user,
                    achievements,
                    "first_blood",
                    challenge_id=challenge_id,
                    context_key=f"challenge:{challenge_id}",
                    event_key=f"first_blood:{challenge_id}",
                )

        db.flush()
        badge_xp = (
            db.query(func.coalesce(func.sum(models.UserAchievement.xp_awarded), 0))
            .filter(models.UserAchievement.user_id == user.id)
            .scalar()
            or 0
        )
        # Recalculate from source records so rerunning migration never duplicates XP.
        user.xp = solved_count * 10 + int(badge_xp)

    db.commit()


def migrate() -> None:
    migrate_prerequisites()
    _ensure_user_columns()
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    required_tables = {"achievements", "user_achievements"}
    missing_tables = required_tables - set(inspector.get_table_names())
    if missing_tables:
        raise RuntimeError(
            "Brakuje tabel: " + ", ".join(sorted(missing_tables))
        )

    db = SessionLocal()
    try:
        achievements = _seed_achievements(db)
        db.commit()
        _backfill_user_progress(db, achievements)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Używana baza SQLite: {DATABASE_PATH}")
    print("Kolumny users.xp / streak: OK")
    print("Tabele achievements / user_achievements: OK")
    print("Odznaki i doświadczenie odtworzone z dotychczasowych rozwiązań.")
    print("Migracja osiągnięć zakończona.")


if __name__ == "__main__":
    migrate()
