"""Multi-level hint management with one-time point penalties."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models


class HintError(Exception):
    """A safe business-rule error for hint unlock actions."""


def save_challenge_hints(
    db: Session,
    challenge: models.Challenge,
    hint_values: dict[int, tuple[str | None, int | None]],
) -> None:
    """Create/update three hint levels; retain unlocked records as inactive history."""
    for level in (1, 2, 3):
        content, penalty = hint_values.get(level, (None, 0))
        content = (content or "").strip()
        penalty = 0 if penalty is None else int(penalty)

        if penalty < 0:
            raise HintError("Koszt podpowiedzi nie może być ujemny.")
        if penalty > 1_000_000:
            raise HintError("Koszt podpowiedzi jest zbyt wysoki.")

        hint = (
            db.query(models.ChallengeHint)
            .filter(
                models.ChallengeHint.challenge_id == challenge.id,
                models.ChallengeHint.level == level,
            )
            .first()
        )

        if content:
            if hint is None:
                hint = models.ChallengeHint(
                    challenge_id=challenge.id,
                    level=level,
                    content=content,
                    penalty_points=penalty,
                    is_active=True,
                )
                db.add(hint)
            else:
                hint.content = content
                hint.penalty_points = penalty
                hint.is_active = True
        elif hint is not None:
            # Keep the row and all prior unlock records; hide it from new players.
            hint.is_active = False


def get_hint_view(
    db: Session,
    challenge: models.Challenge,
    user: models.User | None,
) -> list[dict]:
    """Build a view model that never exposes locked hint text."""
    hints = (
        db.query(models.ChallengeHint)
        .filter(
            models.ChallengeHint.challenge_id == challenge.id,
            models.ChallengeHint.is_active.is_(True),
        )
        .order_by(models.ChallengeHint.level.asc())
        .all()
    )
    if not hints:
        return []

    unlocked_by_hint = {}
    if user is not None:
        unlocks = (
            db.query(models.HintUnlock)
            .filter(
                models.HintUnlock.user_id == user.id,
                models.HintUnlock.hint_id.in_([hint.id for hint in hints]),
            )
            .all()
        )
        unlocked_by_hint = {item.hint_id: item for item in unlocks}

    result = []
    previous_levels_unlocked = True
    for hint in hints:
        unlock = unlocked_by_hint.get(hint.id)
        is_unlocked = unlock is not None
        can_unlock = bool(user is not None and previous_levels_unlocked and not is_unlocked)

        result.append({
            "id": hint.id,
            "level": hint.level,
            "penalty_points": hint.penalty_points,
            "is_unlocked": is_unlocked,
            "can_unlock": can_unlock,
            "content": unlock.hint_content_snapshot if unlock else None,
            "unlocked_at": unlock.unlocked_at if unlock else None,
            "points_deducted": unlock.points_deducted if unlock else 0,
        })

        if not is_unlocked:
            previous_levels_unlocked = False

    return result


def unlock_hint(
    db: Session,
    user: models.User,
    challenge: models.Challenge,
    hint_id: int,
) -> dict:
    """Unlock the next available hint and deduct its cost exactly once."""
    hint = (
        db.query(models.ChallengeHint)
        .filter(
            models.ChallengeHint.id == hint_id,
            models.ChallengeHint.challenge_id == challenge.id,
            models.ChallengeHint.is_active.is_(True),
        )
        .first()
    )
    if hint is None:
        raise HintError("Ta podpowiedź nie istnieje lub nie jest już dostępna.")

    existing = (
        db.query(models.HintUnlock)
        .filter(
            models.HintUnlock.user_id == user.id,
            models.HintUnlock.hint_id == hint.id,
        )
        .first()
    )
    if existing:
        return {
            "already_unlocked": True,
            "points_deducted": 0,
            "message": "Ta podpowiedź jest już odblokowana.",
        }

    earlier_hints = (
        db.query(models.ChallengeHint)
        .filter(
            models.ChallengeHint.challenge_id == challenge.id,
            models.ChallengeHint.is_active.is_(True),
            models.ChallengeHint.level < hint.level,
        )
        .all()
    )
    earlier_ids = [item.id for item in earlier_hints]
    if earlier_ids:
        unlocked_earlier = {
            row[0]
            for row in db.query(models.HintUnlock.hint_id)
            .filter(
                models.HintUnlock.user_id == user.id,
                models.HintUnlock.hint_id.in_(earlier_ids),
            )
            .all()
        }
        if len(unlocked_earlier) != len(earlier_ids):
            raise HintError("Najpierw odblokuj wcześniejszą podpowiedź.")

    current_score = user.score or 0
    cost = hint.penalty_points
    if current_score < cost:
        raise HintError(
            f"Masz {current_score} pkt, a ta podpowiedź kosztuje {cost} pkt. "
            "Zdobądź więcej punktów, aby ją odblokować."
        )

    snapshot = hint.content
    unlock = models.HintUnlock(
        user_id=user.id,
        hint_id=hint.id,
        unlocked_at=datetime.utcnow(),
        points_deducted=cost,
        hint_content_snapshot=snapshot,
    )
    user.score = current_score - cost
    db.add(unlock)

    try:
        db.commit()
        db.refresh(unlock)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.HintUnlock)
            .filter(
                models.HintUnlock.user_id == user.id,
                models.HintUnlock.hint_id == hint.id,
            )
            .first()
        )
        if existing:
            db.refresh(user)
            return {
                "already_unlocked": True,
                "points_deducted": 0,
                "message": "Ta podpowiedź została już wcześniej odblokowana.",
            }
        raise
    except Exception:
        db.rollback()
        raise

    db.refresh(user)
    return {
        "already_unlocked": False,
        "points_deducted": cost,
        "message": (
            "Podpowiedź odblokowana."
            if cost == 0
            else f"Podpowiedź odblokowana. Odjęto {cost} pkt."
        ),
    }
