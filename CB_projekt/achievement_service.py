"""Gamification: XP, levels, streaks and one-time achievement awards."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

XP_PER_SOLVE = 10
XP_PER_LEVEL = 100

ACHIEVEMENT_DEFINITIONS = (
    {
        "code": "first_solve",
        "name": "Pierwszy krok",
        "description": "Rozwiąż swoje pierwsze zadanie CTF.",
        "icon": "🎯",
        "category": "progress",
        "xp_reward": 20,
    },
    {
        "code": "first_blood",
        "name": "First Blood",
        "description": "Jako pierwszy gracz rozwiąż konkretne zadanie.",
        "icon": "🩸",
        "category": "competition",
        "xp_reward": 50,
    },
    {
        "code": "solver_5",
        "name": "Początkujący łowca",
        "description": "Rozwiąż 5 różnych zadań.",
        "icon": "🔎",
        "category": "progress",
        "xp_reward": 25,
    },
    {
        "code": "solver_10",
        "name": "Ekspert CTF",
        "description": "Rozwiąż 10 różnych zadań.",
        "icon": "🏆",
        "category": "progress",
        "xp_reward": 50,
    },
    {
        "code": "streak_3",
        "name": "Trzy dni z rzędu",
        "description": "Rozwiązuj co najmniej jedno zadanie przez 3 kolejne dni.",
        "icon": "🔥",
        "category": "streak",
        "xp_reward": 25,
    },
    {
        "code": "streak_7",
        "name": "Tydzień cybertreningu",
        "description": "Rozwiązuj co najmniej jedno zadanie przez 7 kolejnych dni.",
        "icon": "⚡",
        "category": "streak",
        "xp_reward": 75,
    },
    {
        "code": "category_explorer_3",
        "name": "Wszechstronny badacz",
        "description": "Rozwiąż zadania z 3 różnych kategorii.",
        "icon": "🧭",
        "category": "exploration",
        "xp_reward": 30,
    },
    {
        "code": "completionist",
        "name": "Komplet zadań",
        "description": "Rozwiąż wszystkie zadania dostępne w chwili zdobycia odznaki.",
        "icon": "💎",
        "category": "progress",
        "xp_reward": 100,
    },
)


def level_from_xp(xp: int | None) -> dict:
    total_xp = max(0, int(xp or 0))
    level = total_xp // XP_PER_LEVEL + 1
    progress = total_xp % XP_PER_LEVEL
    return {
        "level": level,
        "xp": total_xp,
        "xp_in_level": progress,
        "xp_to_next_level": XP_PER_LEVEL - progress,
        "level_progress_percent": progress,
        "xp_per_level": XP_PER_LEVEL,
    }


def longest_consecutive_days(days: list[date]) -> int:
    unique_days = sorted(set(days))
    if not unique_days:
        return 0
    longest = current = 1
    for previous, today in zip(unique_days, unique_days[1:]):
        if today == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def update_user_streak(user: models.User, solved_at: datetime) -> int:
    """Count calendar days with at least one successful solve (UTC)."""
    today = solved_at.date()
    previous_day = user.last_solve_date

    if previous_day == today:
        current = user.current_streak or 1
    elif previous_day == today - timedelta(days=1):
        current = (user.current_streak or 0) + 1
    else:
        current = 1

    user.current_streak = current
    user.longest_streak = max(user.longest_streak or 0, current)
    user.last_solve_date = today
    return current


def award_achievement(
    db: Session,
    user: models.User,
    code: str,
    *,
    challenge: models.Challenge | None = None,
    context_key: str = "global",
    event_key: str | None = None,
) -> dict | None:
    """Award a badge once; event_key can enforce a globally unique first event."""
    achievement = (
        db.query(models.Achievement)
        .filter(
            models.Achievement.code == code,
            models.Achievement.is_active.is_(True),
        )
        .first()
    )
    if achievement is None:
        return None

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
        return None

    award = models.UserAchievement(
        user_id=user.id,
        achievement_id=achievement.id,
        challenge_id=challenge.id if challenge else None,
        context_key=context_key,
        event_key=event_key,
        awarded_at=datetime.utcnow(),
        xp_awarded=achievement.xp_reward,
    )
    try:
        # The savepoint allows a competing first-blood award to fail without
        # rolling back the solve and its ordinary XP/score transaction.
        with db.begin_nested():
            db.add(award)
            db.flush()
    except IntegrityError:
        return None

    user.xp = (user.xp or 0) + achievement.xp_reward
    return {
        "code": achievement.code,
        "name": achievement.name,
        "icon": achievement.icon,
        "xp_reward": achievement.xp_reward,
    }


def process_successful_solve(
    db: Session,
    user: models.User,
    challenge: models.Challenge,
    solved_at: datetime,
) -> dict:
    """Award base XP, update streak and evaluate milestones for a new solve."""
    db.flush()

    # XP is separate from competitive points (and from hint penalties).
    user.xp = (user.xp or 0) + XP_PER_SOLVE
    new_streak = update_user_streak(user, solved_at)

    solved_count = (
        db.query(models.Solve)
        .filter(models.Solve.user_id == user.id)
        .count()
    )
    earned = []

    if solved_count == 1:
        item = award_achievement(db, user, "first_solve")
        if item:
            earned.append(item)
    if solved_count >= 5:
        item = award_achievement(db, user, "solver_5")
        if item:
            earned.append(item)
    if solved_count >= 10:
        item = award_achievement(db, user, "solver_10")
        if item:
            earned.append(item)

    # First Blood is unique globally for each challenge.
    first_solve = (
        db.query(models.Solve)
        .filter(models.Solve.challenge_id == challenge.id)
        .order_by(models.Solve.timestamp.asc(), models.Solve.id.asc())
        .first()
    )
    if first_solve and first_solve.user_id == user.id:
        item = award_achievement(
            db,
            user,
            "first_blood",
            challenge=challenge,
            context_key=f"challenge:{challenge.id}",
            event_key=f"first_blood:{challenge.id}",
        )
        if item:
            earned.append(item)

    if new_streak >= 3:
        item = award_achievement(db, user, "streak_3")
        if item:
            earned.append(item)
    if new_streak >= 7:
        item = award_achievement(db, user, "streak_7")
        if item:
            earned.append(item)

    category_count = (
        db.query(models.Challenge.category)
        .join(models.Solve, models.Solve.challenge_id == models.Challenge.id)
        .filter(models.Solve.user_id == user.id)
        .distinct()
        .count()
    )
    if category_count >= 3:
        item = award_achievement(db, user, "category_explorer_3")
        if item:
            earned.append(item)

    total_challenges = db.query(models.Challenge.id).count()
    if total_challenges and solved_count >= total_challenges:
        item = award_achievement(db, user, "completionist")
        if item:
            earned.append(item)

    db.flush()
    level = level_from_xp(user.xp)
    return {
        "base_xp_awarded": XP_PER_SOLVE,
        "bonus_xp_awarded": sum(item["xp_reward"] for item in earned),
        "achievements_awarded": earned,
        "current_streak": user.current_streak,
        "longest_streak": user.longest_streak,
        **level,
    }
