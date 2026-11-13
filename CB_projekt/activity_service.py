"""Privacy-preserving flag submission handling and per-user rate limiting."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from hmac import compare_digest

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from achievement_service import process_successful_solve

FLAG_ATTEMPT_WINDOW_SECONDS = 60
MAX_FLAG_ATTEMPTS_PER_MINUTE = max(
    1, int(os.getenv("CTF_FLAG_ATTEMPTS_PER_MINUTE", "10"))
)


class SubmissionRateLimitError(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(
            f"Przekroczono limit prób. Spróbuj ponownie za {self.retry_after_seconds} s."
        )


def record_flag_submission(
    db: Session,
    user: models.User,
    challenge: models.Challenge,
    submitted_flag: str,
) -> dict:
    """Record a flag attempt and award points exactly once.

    Only the result and timestamp are persisted. The supplied flag is never
    written to the database or application logs.
    """
    existing_solve = (
        db.query(models.Solve)
        .filter(
            models.Solve.user_id == user.id,
            models.Solve.challenge_id == challenge.id,
        )
        .first()
    )
    if existing_solve:
        return {
            "already_solved": True,
            "is_correct": True,
            "points_awarded": 0,
            "submission": None,
        }

    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=FLAG_ATTEMPT_WINDOW_SECONDS)
    recent_count = (
        db.query(func.count(models.Submission.id))
        .filter(
            models.Submission.user_id == user.id,
            models.Submission.submitted_at >= cutoff,
        )
        .scalar()
        or 0
    )

    if recent_count >= MAX_FLAG_ATTEMPTS_PER_MINUTE:
        oldest_recent = (
            db.query(models.Submission.submitted_at)
            .filter(
                models.Submission.user_id == user.id,
                models.Submission.submitted_at >= cutoff,
            )
            .order_by(models.Submission.submitted_at.asc())
            .first()
        )
        retry_after = FLAG_ATTEMPT_WINDOW_SECONDS
        if oldest_recent and oldest_recent[0]:
            retry_after = int(
                (oldest_recent[0] + timedelta(seconds=FLAG_ATTEMPT_WINDOW_SECONDS) - now).total_seconds()
            )
        raise SubmissionRateLimitError(retry_after)

    # Constant-time comparison makes content-dependent timing less useful.
    is_correct = compare_digest(
        (submitted_flag or "").strip().encode("utf-8"),
        (challenge.flag or "").encode("utf-8"),
    )

    submission = models.Submission(
        user_id=user.id,
        challenge_id=challenge.id,
        is_correct=is_correct,
        submitted_at=now,
    )
    db.add(submission)

    points_awarded = 0
    gamification_result = {
        "base_xp_awarded": 0,
        "bonus_xp_awarded": 0,
        "achievements_awarded": [],
        "current_streak": user.current_streak or 0,
        "level": (user.xp or 0) // 100 + 1,
    }
    if is_correct:
        user.score = (user.score or 0) + challenge.points
        points_awarded = challenge.points
        db.add(
            models.Solve(
                user_id=user.id,
                challenge_id=challenge.id,
                timestamp=now,
            )
        )
        gamification_result = process_successful_solve(db, user, challenge, now)

    try:
        db.commit()
        db.refresh(submission)
    except IntegrityError:
        db.rollback()
        # A concurrent correct submission may have created the unique solve
        # first. Do not award points twice or leave a partial history row.
        concurrent_solve = (
            db.query(models.Solve)
            .filter(
                models.Solve.user_id == user.id,
                models.Solve.challenge_id == challenge.id,
            )
            .first()
        )
        if concurrent_solve:
            return {
                "already_solved": True,
                "is_correct": True,
                "points_awarded": 0,
                "submission": None,
            }
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "already_solved": False,
        "is_correct": is_correct,
        "points_awarded": points_awarded,
        "submission": submission,
        **gamification_result,
    }
