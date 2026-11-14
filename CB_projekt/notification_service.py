"""In-app notification delivery and scheduled tournament reminders."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

CATEGORY_FIELDS = {
    "team": "team_enabled",
    "tournament": "tournament_enabled",
    "achievement": "achievement_enabled",
    "announcement": "announcement_enabled",
}


def is_category_enabled(db: Session, user_id: int, category: str) -> bool:
    field = CATEGORY_FIELDS.get(category)
    if field is None:
        raise ValueError(f"Nieznana kategoria powiadomień: {category}")
    preference = (
        db.query(models.NotificationPreference)
        .filter(models.NotificationPreference.user_id == user_id)
        .first()
    )
    return True if preference is None else bool(getattr(preference, field))


def create_notification(
    db: Session,
    user_id: int,
    category: str,
    title: str,
    body: str,
    *,
    target_url: str | None = None,
    dedupe_key: str | None = None,
    announcement_id: int | None = None,
) -> bool:
    """Create one notification; return False when disabled or already delivered."""
    if category not in CATEGORY_FIELDS:
        raise ValueError(f"Nieznana kategoria powiadomień: {category}")
    if not is_category_enabled(db, user_id, category):
        return False
    if dedupe_key and (
        db.query(models.Notification.id)
        .filter(models.Notification.dedupe_key == dedupe_key)
        .first()
    ):
        return False

    notification = models.Notification(
        user_id=user_id,
        category=category,
        title=(title or "").strip()[:140],
        body=(body or "").strip(),
        target_url=target_url,
        dedupe_key=dedupe_key,
        announcement_id=announcement_id,
        is_read=False,
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return False
    return True


def _reserve_dispatch(db: Session, event_key: str) -> bool:
    existing = (
        db.query(models.NotificationDispatch.id)
        .filter(models.NotificationDispatch.event_key == event_key)
        .first()
    )
    if existing:
        return False
    try:
        with db.begin_nested():
            db.add(models.NotificationDispatch(event_key=event_key))
            db.flush()
    except IntegrityError:
        return False
    return True


def notify_users_once(
    db: Session,
    user_ids: list[int],
    category: str,
    title: str,
    body: str,
    *,
    target_url: str | None = None,
    event_key: str,
    announcement_id: int | None = None,
) -> int:
    """Broadcast to a fixed audience once. Preferences are applied per user."""
    if not _reserve_dispatch(db, event_key):
        return 0
    delivered = 0
    for user_id in sorted(set(user_ids)):
        if create_notification(
            db,
            user_id,
            category,
            title,
            body,
            target_url=target_url,
            dedupe_key=f"{event_key}:user:{user_id}",
            announcement_id=announcement_id,
        ):
            delivered += 1
    return delivered


def notify_all_users_once(
    db: Session,
    category: str,
    title: str,
    body: str,
    *,
    target_url: str | None = None,
    event_key: str,
    announcement_id: int | None = None,
) -> int:
    user_ids = [row[0] for row in db.query(models.User.id).order_by(models.User.id.asc()).all()]
    return notify_users_once(
        db,
        user_ids,
        category,
        title,
        body,
        target_url=target_url,
        event_key=event_key,
        announcement_id=announcement_id,
    )


def _tournament_recipient_ids(db: Session, tournament_id: int) -> list[int]:
    return [
        row[0]
        for row in (
            db.query(models.TournamentParticipant.user_id)
            .filter(models.TournamentParticipant.tournament_id == tournament_id)
            .order_by(models.TournamentParticipant.user_id.asc())
            .all()
        )
    ]


def process_due_tournament_notifications(
    db: Session,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send 24h/1h/start/end notices, automatically finishing expired events."""
    now = now or datetime.utcnow()
    result = {"24h": 0, "1h": 0, "started": 0, "finished": 0}
    tournaments = (
        db.query(models.Tournament)
        .filter(models.Tournament.status == "open")
        .order_by(models.Tournament.id.asc())
        .all()
    )

    for tournament in tournaments:
        tournament_id = tournament.id
        recipients = _tournament_recipient_ids(db, tournament_id)
        target = f"/tournaments/{tournament_id}"
        starts_in = tournament.starts_at - now

        if timedelta(hours=1) < starts_in <= timedelta(hours=24):
            result["24h"] += notify_users_once(
                db,
                recipients,
                "tournament",
                f"Turniej „{tournament.title}” już jutro",
                f"Do rozpoczęcia turnieju pozostało mniej niż 24 godziny. Sprawdź zadania i przygotuj się do rywalizacji.",
                target_url=target,
                event_key=f"tournament:{tournament_id}:reminder:24h",
            )
        elif timedelta(0) < starts_in <= timedelta(hours=1):
            result["1h"] += notify_users_once(
                db,
                recipients,
                "tournament",
                f"Turniej „{tournament.title}” startuje wkrótce",
                "Do rozpoczęcia turnieju pozostała maksymalnie godzina.",
                target_url=target,
                event_key=f"tournament:{tournament_id}:reminder:1h",
            )

        if tournament.starts_at <= now < tournament.ends_at:
            result["started"] += notify_users_once(
                db,
                recipients,
                "tournament",
                f"Turniej „{tournament.title}” właśnie wystartował",
                "Zawody są już aktywne. Powodzenia i udanej rywalizacji!",
                target_url=target,
                event_key=f"tournament:{tournament_id}:started",
            )

        if tournament.ends_at <= now:
            tournament.status = "finished"
            result["finished"] += notify_users_once(
                db,
                recipients,
                "tournament",
                f"Turniej „{tournament.title}” został zakończony",
                "Zawody dobiegły końca. Otwórz stronę turnieju, aby zobaczyć końcowy ranking.",
                target_url=target,
                event_key=f"tournament:{tournament_id}:finished",
            )

    return result
