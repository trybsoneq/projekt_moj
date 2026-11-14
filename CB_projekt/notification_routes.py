"""Routes for personal notification inbox and administrator announcements."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from notification_service import notify_all_users_once
from security import require_admin, require_user

router = APIRouter()


def _redirect(path: str, message: str | None = None) -> RedirectResponse:
    if message:
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}message={quote(message)}"
    return RedirectResponse(url=path, status_code=302)


def _get_preferences(db: Session, user_id: int) -> models.NotificationPreference:
    preferences = (
        db.query(models.NotificationPreference)
        .filter(models.NotificationPreference.user_id == user_id)
        .first()
    )
    if preferences is None:
        preferences = models.NotificationPreference(user_id=user_id)
        db.add(preferences)
        db.flush()
    return preferences


@router.get("/notifications")
def show_notifications(
    request: Request,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    preferences = _get_preferences(db, current_user.id)
    notifications = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
        .limit(100)
        .all()
    )
    unread_count = (
        db.query(func.count(models.Notification.id))
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.is_read.is_(False),
        )
        .scalar()
        or 0
    )
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/notifications.html",
        {
            "request": request,
            "username": current_user.username,
            "is_admin": current_user.role == "admin",
            "user_points": current_user.score or 0,
            "active_page": "notifications",
            "notifications": notifications,
            "unread_count": unread_count,
            "preferences": preferences,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Powiadomienie nie istnieje.")
    notification.is_read = True
    db.commit()
    return RedirectResponse(url=notification.target_url or "/notifications", status_code=302)


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.is_read.is_(False),
        )
        .update({models.Notification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return _redirect("/notifications", "Oznaczono wszystkie powiadomienia jako przeczytane.")


@router.post("/notifications/settings")
def update_notification_settings(
    team_enabled: bool = Form(False),
    tournament_enabled: bool = Form(False),
    achievement_enabled: bool = Form(False),
    announcement_enabled: bool = Form(False),
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    preferences = _get_preferences(db, current_user.id)
    preferences.team_enabled = team_enabled
    preferences.tournament_enabled = tournament_enabled
    preferences.achievement_enabled = achievement_enabled
    preferences.announcement_enabled = announcement_enabled
    preferences.updated_at = datetime.utcnow()
    db.commit()
    return _redirect("/notifications", "Zapisano ustawienia powiadomień.")


@router.get("/admin/announcements")
def admin_announcements(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.Announcement,
            func.count(models.Notification.id).label("recipient_count"),
        )
        .outerjoin(
            models.Notification,
            models.Notification.announcement_id == models.Announcement.id,
        )
        .group_by(models.Announcement.id)
        .order_by(models.Announcement.created_at.desc())
        .all()
    )
    announcements = [
        {
            "announcement": announcement,
            "recipient_count": recipient_count,
        }
        for announcement, recipient_count in rows
    ]
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/admin_announcements.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "admin_announcements",
            "announcements": announcements,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/admin/announcements/create")
def create_announcement(
    title: str = Form(...),
    body: str = Form(...),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title = (title or "").strip()
    body = (body or "").strip()
    if len(title) < 3 or len(title) > 140:
        return _redirect("/admin/announcements", "Tytuł komunikatu musi mieć od 3 do 140 znaków.")
    if len(body) < 5 or len(body) > 3000:
        return _redirect("/admin/announcements", "Treść komunikatu musi mieć od 5 do 3000 znaków.")

    announcement = models.Announcement(
        title=title,
        body=body,
        created_by_user_id=current_admin.id,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(announcement)
    db.flush()
    notify_all_users_once(
        db,
        "announcement",
        title,
        body,
        target_url="/notifications",
        event_key=f"announcement:{announcement.id}:published",
        announcement_id=announcement.id,
    )
    announcement.sent_at = datetime.utcnow()
    db.commit()
    return _redirect("/admin/announcements", "Opublikowano komunikat i wysłano powiadomienia.")


@router.post("/admin/announcements/{announcement_id}/archive")
def archive_announcement(
    announcement_id: int,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    announcement = (
        db.query(models.Announcement)
        .filter(models.Announcement.id == announcement_id)
        .first()
    )
    if announcement is None:
        raise HTTPException(status_code=404, detail="Komunikat nie istnieje.")
    announcement.is_active = False
    db.commit()
    return _redirect("/admin/announcements", "Zarchiwizowano komunikat.")
