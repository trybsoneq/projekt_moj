"""Analytics pages and CSV/PDF export endpoints."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

import models
from analytics_export import create_csv, create_pdf
from analytics_service import (
    admin_analytics,
    admin_report_rows,
    parse_date_range,
    player_analytics,
    team_analytics,
)
from database import get_db
from security import require_admin, require_user

router = APIRouter()


def _admin_data(db: Session, date_from: str | None, date_to: str | None):
    try:
        start_at, end_at, start_date, end_date = parse_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = admin_analytics(db, start_at, end_at)
    data["date_from"] = start_date.isoformat() if start_date else ""
    data["date_to"] = end_date.isoformat() if end_date else ""
    data["max_daily_attempts"] = max(
        (row["attempts"] for row in data["daily"]),
        default=0,
    )
    data["max_category_attempts"] = max(
        (row["attempts"] for row in data["categories"]),
        default=0,
    )
    return data


def _player_summary_rows(data: dict) -> list[list[str]]:
    return [
        ["Metryka", "Wartość"],
        ["Użytkownik", data["username"]],
        ["Punkty globalne", str(data["score"])],
        ["XP", str(data["xp"])],
        ["Poziom", str(data["level"])],
        ["Rozwiązane zadania", str(data["solves"])],
        ["Wszystkie próby", str(data["attempts"])],
        ["Poprawne próby", str(data["correct"])],
        ["Niepoprawne próby", str(data["incorrect"])],
        ["Skuteczność (%)", str(data["accuracy"])],
        ["Aktualna seria", str(data["current_streak"])],
        ["Najdłuższa seria", str(data["longest_streak"])],
    ]


def _player_category_rows(data: dict) -> list[list[str]]:
    return [["Kategoria", "Rozwiązania", "Dostępne zadania", "Postęp (%)"]] + [
        [r["category"], str(r["solves"]), str(r["total"]), str(r["progress"])]
        for r in data["categories"]
    ]


def _player_tournament_rows(data: dict) -> list[list[str]]:
    return [["Turniej", "Status", "Rozwiązania", "Punkty"]] + [
        [r["title"], r["status"], str(r["solves"]), str(r["points"])]
        for r in data["tournaments"]
    ]


def _player_report_rows(data: dict) -> list[list[str]]:
    return _player_summary_rows(data) + [["", ""]] + _player_category_rows(data) + [["", ""]] + _player_tournament_rows(data)


def _team_summary_rows(data: dict) -> list[list[str]]:
    return [
        ["Metryka drużyny", "Wartość"],
        ["Drużyna", data["team"].name],
        ["Członkowie", str(data["member_count"])],
        ["Próby członków", str(data["total_attempts"])],
        ["Rozwiązania członków", str(data["total_solves"])],
        ["Punkty turniejowe", str(data["tournament_points"])],
    ]


def _team_member_rows(data: dict) -> list[list[str]]:
    return [["Członek", "Rola", "Punkty globalne", "XP", "Próby", "Rozwiązania", "Punkty turniejowe"]] + [[
        r["username"], r["role"], str(r["score"]), str(r["xp"]),
        str(r["attempts"]), str(r["solves"]), str(r["tournament_points"]),
    ] for r in data["members"]]


def _team_tournament_rows(data: dict) -> list[list[str]]:
    return [["Turniej", "Status", "Rozwiązania", "Punkty"]] + [
        [r["title"], r["status"], str(r["solves"]), str(r["points"])]
        for r in data["tournaments"]
    ]


def _team_report_rows(data: dict) -> list[list[str]]:
    return _team_summary_rows(data) + [["", ""]] + _team_member_rows(data) + [["", ""]] + _team_tournament_rows(data)


@router.get("/admin/analytics")
def show_admin_analytics(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = _admin_data(db, date_from, date_to)
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/admin_analytics.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "admin_analytics",
            "analytics": data,
        },
    )


@router.get("/admin/analytics/export.csv")
def export_admin_csv(
    date_from: str | None = None,
    date_to: str | None = None,
    kind: str = "summary",
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = _admin_data(db, date_from, date_to)
    try:
        rows = admin_report_rows(data, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = create_csv(rows)
    filename = f"cybersim_{kind}_{datetime.utcnow():%Y%m%d_%H%M%S}.csv"
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/analytics/export.pdf")
def export_admin_pdf(
    date_from: str | None = None,
    date_to: str | None = None,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = _admin_data(db, date_from, date_to)
    sections = [
        ("Podsumowanie platformy", admin_report_rows(data, "summary")),
        ("Aktywność według kategorii", admin_report_rows(data, "categories")),
        ("Statystyki zadań", admin_report_rows(data, "challenges")),
        ("Najaktywniejsi użytkownicy", admin_report_rows(data, "users")),
        ("Drużyny", admin_report_rows(data, "teams")),
        ("Turnieje", admin_report_rows(data, "tournaments")),
        ("Aktywność dzienna (UTC)", admin_report_rows(data, "daily")),
    ]
    try:
        payload = create_pdf("CyberSim – raport analityczny", sections)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Eksport PDF wymaga pakietu reportlab.") from exc
    filename = f"cybersim_analytics_{datetime.utcnow():%Y%m%d_%H%M%S}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/profile/analytics")
def show_player_analytics(
    request: Request,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    data = player_analytics(db, current_user)
    data["max_daily_attempts"] = max((row["attempts"] for row in data["daily"]), default=0)
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/player_analytics.html",
        {
            "request": request,
            "username": current_user.username,
            "is_admin": current_user.role == "admin",
            "user_points": current_user.score or 0,
            "active_page": "profile_analytics",
            "analytics": data,
        },
    )


@router.get("/profile/analytics/export.csv")
def export_player_csv(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    data = player_analytics(db, current_user)
    rows = _player_report_rows(data)
    payload = create_csv(rows)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cybersim_moje_statystyki.csv"'},
    )


@router.get("/profile/analytics/export.pdf")
def export_player_pdf(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    data = player_analytics(db, current_user)
    sections = [
        ("Podsumowanie gracza", _player_summary_rows(data)),
        ("Postęp według kategorii", _player_category_rows(data)),
        ("Historia turniejów", _player_tournament_rows(data)),
        ("Aktywność dzienna (UTC)", [
            ["Data", "Próby", "Poprawne"],
            *[[r["date"], str(r["attempts"]), str(r["correct"])] for r in data["daily"]],
        ]),
    ]
    payload = create_pdf("CyberSim – statystyki gracza", sections)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cybersim_moje_statystyki.pdf"'},
    )


def _current_team(db: Session, user_id: int) -> models.Team | None:
    membership = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.user_id == user_id)
        .first()
    )
    if membership is None:
        return None
    return db.query(models.Team).filter(models.Team.id == membership.team_id).first()


@router.get("/teams/analytics")
def show_team_analytics(
    request: Request,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    team = _current_team(db, current_user.id)
    if team is None:
        return RedirectResponse(
            url="/teams?message=" + quote("Nie należysz do żadnej drużyny."),
            status_code=302,
        )
    data = team_analytics(db, team)
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/team_analytics.html",
        {
            "request": request,
            "username": current_user.username,
            "is_admin": current_user.role == "admin",
            "user_points": current_user.score or 0,
            "active_page": "team_analytics",
            "analytics": data,
            "is_leader": (
                db.query(models.TeamMember)
                .filter_by(team_id=team.id, user_id=current_user.id, role="leader")
                .first()
                is not None
            ),
        },
    )


@router.get("/teams/analytics/export.csv")
def export_team_csv(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    team = _current_team(db, current_user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="Nie należysz do żadnej drużyny.")
    payload = create_csv(_team_report_rows(team_analytics(db, team)))
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cybersim_statystyki_druzyny.csv"'},
    )


@router.get("/teams/analytics/export.pdf")
def export_team_pdf(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    team = _current_team(db, current_user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="Nie należysz do żadnej drużyny.")
    data = team_analytics(db, team)
    sections = [
        ("Podsumowanie drużyny", _team_summary_rows(data)),
        ("Aktywność członków", _team_member_rows(data)),
        ("Wyniki turniejowe", _team_tournament_rows(data)),
    ]
    payload = create_pdf("CyberSim – statystyki druzyny", sections)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cybersim_statystyki_druzyny.pdf"'},
    )
