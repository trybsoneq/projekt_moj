"""HTTP routes for team management and CTF tournaments."""
from __future__ import annotations

import secrets
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from security import get_current_user, require_admin, require_user
from tournament_service import (
    TournamentError,
    join_tournament,
    registered_count,
    tournament_leaderboards,
)

router = APIRouter()


def _redirect(path: str, message: str | None = None) -> RedirectResponse:
    if message:
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}message={quote(message)}"
    return RedirectResponse(url=path, status_code=302)


def _team_membership(db: Session, user_id: int):
    return (
        db.query(models.TeamMember)
        .filter(models.TeamMember.user_id == user_id)
        .first()
    )


def _team_has_live_event(db: Session, team_id: int, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    return (
        db.query(models.TournamentTeamParticipant)
        .join(
            models.Tournament,
            models.Tournament.id == models.TournamentTeamParticipant.tournament_id,
        )
        .filter(
            models.TournamentTeamParticipant.team_id == team_id,
            models.Tournament.status == "open",
            models.Tournament.starts_at <= now,
            models.Tournament.ends_at > now,
        )
        .first()
        is not None
    )


@router.get("/teams")
def show_teams(
    request: Request,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    membership = _team_membership(db, current_user.id)
    team = (
        db.query(models.Team)
        .filter(models.Team.id == membership.team_id)
        .first()
        if membership
        else None
    )

    members = []
    sent_invitations = []
    if team:
        rows = (
            db.query(models.TeamMember, models.User)
            .join(models.User, models.User.id == models.TeamMember.user_id)
            .filter(models.TeamMember.team_id == team.id)
            .order_by(models.TeamMember.role.desc(), models.User.username.asc())
            .all()
        )
        members = [
            {"user_id": member.user_id, "username": user.username, "role": member.role}
            for member, user in rows
        ]
        if membership.role == "leader":
            rows = (
                db.query(models.TeamInvitation, models.User)
                .join(models.User, models.User.id == models.TeamInvitation.invited_user_id)
                .filter(
                    models.TeamInvitation.team_id == team.id,
                    models.TeamInvitation.status == "pending",
                )
                .order_by(models.TeamInvitation.created_at.desc())
                .all()
            )
            sent_invitations = [
                {"id": invitation.id, "username": user.username}
                for invitation, user in rows
            ]

    incoming_rows = (
        db.query(models.TeamInvitation, models.Team)
        .join(models.Team, models.Team.id == models.TeamInvitation.team_id)
        .filter(
            models.TeamInvitation.invited_user_id == current_user.id,
            models.TeamInvitation.status == "pending",
        )
        .order_by(models.TeamInvitation.created_at.desc())
        .all()
    )
    incoming_invitations = [
        {"id": invitation.id, "team_name": invited_team.name}
        for invitation, invited_team in incoming_rows
    ]

    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/teams.html",
        {
            "request": request,
            "username": current_user.username,
            "is_admin": current_user.role == "admin",
            "user_points": current_user.score or 0,
            "active_page": "teams",
            "team": team,
            "membership": membership,
            "current_user_id": current_user.id,
            "members": members,
            "sent_invitations": sent_invitations,
            "incoming_invitations": incoming_invitations,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/teams/create")
def create_team(
    name: str = Form(...),
    description: str = Form(""),
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    name = (name or "").strip()
    description = (description or "").strip()
    if len(name) < 3 or len(name) > 60:
        return _redirect("/teams", "Nazwa drużyny musi mieć od 3 do 60 znaków.")
    if _team_membership(db, current_user.id):
        return _redirect("/teams", "Możesz należeć tylko do jednej drużyny.")
    if db.query(models.Team).filter(models.Team.name == name).first():
        return _redirect("/teams", "Drużyna o takiej nazwie już istnieje.")

    team = models.Team(
        name=name,
        description=description or None,
        invite_code=secrets.token_urlsafe(18),
        owner_user_id=current_user.id,
    )
    db.add(team)
    db.flush()
    db.add(models.TeamMember(team_id=team.id, user_id=current_user.id, role="leader"))
    db.commit()
    return _redirect("/teams", "Drużyna została utworzona.")


@router.post("/teams/invite")
def invite_to_team(
    username: str = Form(...),
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    membership = _team_membership(db, current_user.id)
    if membership is None or membership.role != "leader":
        return _redirect("/teams", "Zapraszać nowych członków może tylko lider drużyny.")
    invited_username = (username or "").strip()
    target = (
        db.query(models.User)
        .filter(models.User.username == invited_username)
        .first()
    )
    if target is None:
        return _redirect("/teams", "Nie znaleziono użytkownika o takiej nazwie.")
    if target.id == current_user.id:
        return _redirect("/teams", "Nie możesz zaprosić samego siebie.")
    if _team_membership(db, target.id):
        return _redirect("/teams", "Ten użytkownik należy już do drużyny.")
    pending = (
        db.query(models.TeamInvitation)
        .filter(
            models.TeamInvitation.team_id == membership.team_id,
            models.TeamInvitation.invited_user_id == target.id,
            models.TeamInvitation.status == "pending",
        )
        .first()
    )
    if pending:
        return _redirect("/teams", "Zaproszenie do tego użytkownika już oczekuje na odpowiedź.")

    db.add(models.TeamInvitation(
        team_id=membership.team_id,
        invited_user_id=target.id,
        invited_by_user_id=current_user.id,
        status="pending",
    ))
    db.commit()
    return _redirect("/teams", f"Wysłano zaproszenie do użytkownika {target.username}.")


@router.post("/teams/invitations/{invitation_id}/accept")
def accept_team_invitation(
    invitation_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    invitation = (
        db.query(models.TeamInvitation)
        .filter(
            models.TeamInvitation.id == invitation_id,
            models.TeamInvitation.invited_user_id == current_user.id,
            models.TeamInvitation.status == "pending",
        )
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Zaproszenie nie istnieje lub nie jest już aktywne.")
    if _team_membership(db, current_user.id):
        return _redirect("/teams", "Najpierw opuść obecną drużynę.")
    if _team_has_live_event(db, invitation.team_id):
        return _redirect("/teams", "Nie można zmieniać składu drużyny podczas trwającego turnieju.")

    invitation.status = "accepted"
    db.add(models.TeamMember(
        team_id=invitation.team_id,
        user_id=current_user.id,
        role="member",
    ))
    # If the team has registered for a future event, include the new member
    # in the event's individual standings before it starts.
    now = datetime.utcnow()
    registrations = (
        db.query(models.TournamentTeamParticipant, models.Tournament)
        .join(
            models.Tournament,
            models.Tournament.id == models.TournamentTeamParticipant.tournament_id,
        )
        .filter(
            models.TournamentTeamParticipant.team_id == invitation.team_id,
            models.Tournament.status == "open",
            models.Tournament.starts_at > now,
            models.Tournament.ends_at > now,
        )
        .all()
    )
    for registration, tournament in registrations:
        already = (
            db.query(models.TournamentParticipant)
            .filter_by(tournament_id=tournament.id, user_id=current_user.id)
            .first()
        )
        if already is None:
            db.add(models.TournamentParticipant(
                tournament_id=tournament.id,
                user_id=current_user.id,
            ))
    db.commit()
    return _redirect("/teams", "Dołączono do drużyny.")


@router.post("/teams/invitations/{invitation_id}/decline")
def decline_team_invitation(
    invitation_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    invitation = (
        db.query(models.TeamInvitation)
        .filter(
            models.TeamInvitation.id == invitation_id,
            models.TeamInvitation.invited_user_id == current_user.id,
            models.TeamInvitation.status == "pending",
        )
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Zaproszenie nie istnieje lub nie jest już aktywne.")
    invitation.status = "declined"
    db.commit()
    return _redirect("/teams", "Odrzucono zaproszenie.")


@router.post("/teams/transfer")
def transfer_team_leadership(
    target_user_id: int = Form(...),
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    membership = _team_membership(db, current_user.id)
    if membership is None or membership.role != "leader":
        return _redirect("/teams", "Tylko lider może przekazać przywództwo.")
    target_membership = (
        db.query(models.TeamMember)
        .filter_by(team_id=membership.team_id, user_id=target_user_id)
        .first()
    )
    if target_membership is None:
        return _redirect("/teams", "Wybrany użytkownik nie należy do tej drużyny.")

    target_membership.role = "leader"
    membership.role = "member"
    team = db.query(models.Team).filter(models.Team.id == membership.team_id).first()
    team.owner_user_id = target_user_id
    db.commit()
    return _redirect("/teams", "Przekazano rolę lidera drużyny.")


@router.post("/teams/leave")
def leave_team(
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    membership = _team_membership(db, current_user.id)
    if membership is None:
        return _redirect("/teams", "Nie należysz do żadnej drużyny.")
    team_id = membership.team_id
    if _team_has_live_event(db, team_id):
        return _redirect("/teams", "Nie można zmieniać składu podczas trwającego turnieju.")

    if membership.role == "leader":
        other_members = (
            db.query(models.TeamMember)
            .filter(
                models.TeamMember.team_id == team_id,
                models.TeamMember.user_id != current_user.id,
            )
            .count()
        )
        if other_members:
            return _redirect("/teams", "Najpierw przekaż rolę lidera innemu członkowi drużyny.")
        has_history = (
            db.query(models.TournamentTeamParticipant)
            .filter(models.TournamentTeamParticipant.team_id == team_id)
            .first()
        )
        if has_history:
            return _redirect("/teams", "Drużyna ma historię turniejową i nie może zostać usunięta.")
        db.query(models.TeamInvitation).filter(models.TeamInvitation.team_id == team_id).delete()
        db.delete(membership)
        team = db.query(models.Team).filter(models.Team.id == team_id).first()
        if team:
            db.delete(team)
    else:
        # Remove the departing member from future event rosters, but retain
        # their historical participation in completed tournaments.
        future_registrations = (
            db.query(models.TournamentTeamParticipant, models.Tournament)
            .join(
                models.Tournament,
                models.Tournament.id == models.TournamentTeamParticipant.tournament_id,
            )
            .filter(
                models.TournamentTeamParticipant.team_id == team_id,
                models.Tournament.status == "open",
                models.Tournament.starts_at > datetime.utcnow(),
            )
            .all()
        )
        for registration, tournament in future_registrations:
            db.query(models.TournamentParticipant).filter_by(
                tournament_id=tournament.id,
                user_id=current_user.id,
            ).delete(synchronize_session=False)
        db.delete(membership)
    db.commit()
    return _redirect("/teams", "Opuściłeś drużynę.")


@router.get("/tournaments")
def list_tournaments(
    request: Request,
    current_user: models.User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tournaments = (
        db.query(models.Tournament)
        .order_by(models.Tournament.starts_at.desc(), models.Tournament.id.desc())
        .all()
    )
    individual_ids = set()
    if current_user:
        individual_ids = {
            row[0]
            for row in db.query(models.TournamentParticipant.tournament_id)
            .filter(models.TournamentParticipant.user_id == current_user.id)
            .all()
        }
    membership = _team_membership(db, current_user.id) if current_user else None
    team_ids = set()
    if membership:
        team_ids = {
            row[0]
            for row in db.query(models.TournamentTeamParticipant.tournament_id)
            .filter(models.TournamentTeamParticipant.team_id == membership.team_id)
            .all()
        }

    tournament_rows = []
    for tournament in tournaments:
        selected_challenges = (
            db.query(models.TournamentChallenge)
            .filter(models.TournamentChallenge.tournament_id == tournament.id)
            .count()
        )
        tournament_rows.append({
            "tournament": tournament,
            "participant_count": registered_count(db, tournament),
            "challenge_count": selected_challenges,
            "is_joined": (
                tournament.id in individual_ids
                if tournament.competition_type == "individual"
                else tournament.id in team_ids
            ),
        })

    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/tournaments.html",
        {
            "request": request,
            "username": current_user.username if current_user else None,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "user_points": current_user.score or 0 if current_user else 0,
            "active_page": "tournaments",
            "tournament_rows": tournament_rows,
            "now": datetime.utcnow(),
            "message": request.query_params.get("message"),
        },
    )


@router.get("/tournaments/{tournament_id}")
def tournament_detail(
    request: Request,
    tournament_id: int,
    current_user: models.User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Turniej nie istnieje.")

    challenge_rows = (
        db.query(models.TournamentChallenge, models.Challenge)
        .join(models.Challenge, models.Challenge.id == models.TournamentChallenge.challenge_id)
        .filter(models.TournamentChallenge.tournament_id == tournament.id)
        .order_by(models.Challenge.title.asc())
        .all()
    )
    individual_board, team_board = tournament_leaderboards(db, tournament)
    membership = _team_membership(db, current_user.id) if current_user else None
    participant = (
        db.query(models.TournamentParticipant)
        .filter_by(tournament_id=tournament.id, user_id=current_user.id)
        .first()
        if current_user
        else None
    )
    team_registered = False
    current_team = None
    if membership:
        current_team = db.query(models.Team).filter_by(id=membership.team_id).first()
        team_registered = (
            db.query(models.TournamentTeamParticipant)
            .filter_by(tournament_id=tournament.id, team_id=membership.team_id)
            .first()
            is not None
        )

    now = datetime.utcnow()
    can_join = bool(current_user and tournament.status == "open" and now < tournament.starts_at and now < tournament.ends_at)
    is_joined = participant is not None if tournament.competition_type == "individual" else team_registered
    can_manage_team_entry = bool(
        tournament.competition_type == "team"
        and membership
        and membership.role == "leader"
        and not team_registered
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/tournament_detail.html",
        {
            "request": request,
            "username": current_user.username if current_user else None,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "user_points": current_user.score or 0 if current_user else 0,
            "active_page": "tournaments",
            "tournament": tournament,
            "challenge_rows": challenge_rows,
            "individual_board": individual_board,
            "team_board": team_board,
            "participant_count": registered_count(db, tournament),
            "is_joined": is_joined,
            "can_join": can_join,
            "can_manage_team_entry": can_manage_team_entry,
            "membership": membership,
            "current_team": current_team,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/tournaments/{tournament_id}/join")
def join_tournament_route(
    tournament_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).first()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Turniej nie istnieje.")
    try:
        join_tournament(db, current_user, tournament)
        db.commit()
    except TournamentError as exc:
        db.rollback()
        return _redirect(f"/tournaments/{tournament_id}", str(exc))
    except Exception:
        db.rollback()
        raise
    return _redirect(f"/tournaments/{tournament_id}", "Zapisano do turnieju.")


@router.post("/tournaments/{tournament_id}/leave")
def leave_tournament_route(
    tournament_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).first()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Turniej nie istnieje.")
    if tournament.status != "open" or datetime.utcnow() >= tournament.starts_at:
        return _redirect(f"/tournaments/{tournament_id}", "Po rozpoczęciu turnieju nie można anulować udziału.")
    if tournament.competition_type == "individual":
        participant = (
            db.query(models.TournamentParticipant)
            .filter_by(tournament_id=tournament.id, user_id=current_user.id)
            .first()
        )
        if participant:
            db.delete(participant)
    else:
        membership = _team_membership(db, current_user.id)
        if membership is None or membership.role != "leader":
            return _redirect(f"/tournaments/{tournament_id}", "Zgłoszenie drużyny może anulować tylko jej lider.")
        registration = (
            db.query(models.TournamentTeamParticipant)
            .filter_by(tournament_id=tournament.id, team_id=membership.team_id)
            .first()
        )
        if registration:
            team_user_ids = [
                row[0]
                for row in db.query(models.TeamMember.user_id)
                .filter(models.TeamMember.team_id == membership.team_id)
                .all()
            ]
            db.delete(registration)
            if team_user_ids:
                db.query(models.TournamentParticipant).filter(
                    models.TournamentParticipant.tournament_id == tournament.id,
                    models.TournamentParticipant.user_id.in_(team_user_ids),
                ).delete(synchronize_session=False)
    db.commit()
    return _redirect(f"/tournaments/{tournament_id}", "Anulowano udział w turnieju.")


@router.get("/admin/tournaments")
def admin_tournaments(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tournaments = (
        db.query(models.Tournament)
        .order_by(models.Tournament.created_at.desc())
        .all()
    )
    tournament_rows = []
    for tournament in tournaments:
        tournament_rows.append({
            "tournament": tournament,
            "participant_count": registered_count(db, tournament),
            "challenge_count": (
                db.query(models.TournamentChallenge)
                .filter(models.TournamentChallenge.tournament_id == tournament.id)
                .count()
            ),
        })
    challenges = db.query(models.Challenge).order_by(models.Challenge.title.asc()).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/admin_tournaments.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "admin_tournaments",
            "tournament_rows": tournament_rows,
            "challenges": challenges,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/admin/tournaments/create")
def create_tournament(
    title: str = Form(...),
    description: str = Form(""),
    competition_type: str = Form("individual"),
    starts_at_text: str = Form(..., alias="starts_at"),
    ends_at_text: str = Form(..., alias="ends_at"),
    max_participants_text: str = Form(""),
    challenge_ids: list[int] = Form([]),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    title = (title or "").strip()
    description = (description or "").strip()
    if len(title) < 3 or len(title) > 120:
        return _redirect("/admin/tournaments", "Tytuł turnieju musi mieć od 3 do 120 znaków.")
    if competition_type not in {"individual", "team"}:
        return _redirect("/admin/tournaments", "Nieprawidłowy typ turnieju.")
    try:
        starts_at = datetime.fromisoformat(starts_at_text)
        ends_at = datetime.fromisoformat(ends_at_text)
    except (TypeError, ValueError):
        return _redirect("/admin/tournaments", "Podaj poprawne daty rozpoczęcia i zakończenia (UTC).")
    if ends_at <= starts_at:
        return _redirect("/admin/tournaments", "Data zakończenia musi być późniejsza niż data rozpoczęcia.")
    try:
        max_participants = int(max_participants_text) if max_participants_text.strip() else None
    except ValueError:
        return _redirect("/admin/tournaments", "Limit uczestników musi być liczbą całkowitą.")
    if max_participants is not None and max_participants < 1:
        return _redirect("/admin/tournaments", "Limit uczestników musi wynosić co najmniej 1.")

    selected_ids = sorted(set(challenge_ids or []))
    if not selected_ids:
        return _redirect("/admin/tournaments", "Wybierz co najmniej jedno zadanie do turnieju.")
    selected_challenges = (
        db.query(models.Challenge)
        .filter(models.Challenge.id.in_(selected_ids))
        .all()
    )
    if len(selected_challenges) != len(selected_ids):
        return _redirect("/admin/tournaments", "Jedno z wybranych zadań nie istnieje.")

    tournament = models.Tournament(
        title=title,
        description=description or None,
        competition_type=competition_type,
        starts_at=starts_at,
        ends_at=ends_at,
        status="draft",
        max_participants=max_participants,
        created_by_user_id=current_admin.id,
    )
    db.add(tournament)
    db.flush()
    for challenge in selected_challenges:
        db.add(models.TournamentChallenge(
            tournament_id=tournament.id,
            challenge_id=challenge.id,
            points=challenge.points,
        ))
    db.commit()
    return _redirect("/admin/tournaments", "Utworzono turniej. Otwórz zapisy, gdy będzie gotowy.")


@router.post("/admin/tournaments/{tournament_id}/status")
def update_tournament_status(
    tournament_id: int,
    status: str = Form(...),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).first()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Turniej nie istnieje.")
    if status not in {"draft", "open", "finished"}:
        return _redirect("/admin/tournaments", "Nieprawidłowy status turnieju.")
    if status == "open" and datetime.utcnow() >= tournament.ends_at:
        return _redirect("/admin/tournaments", "Nie można otworzyć zapisów po dacie zakończenia.")
    tournament.status = status
    db.commit()
    return _redirect("/admin/tournaments", f"Zmieniono status turnieju „{tournament.title}”.")


@router.get("/admin/tournaments/{tournament_id}")
def admin_tournament_detail(
    request: Request,
    tournament_id: int,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tournament = db.query(models.Tournament).filter_by(id=tournament_id).first()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Turniej nie istnieje.")
    individual_board, team_board = tournament_leaderboards(db, tournament)
    participant_rows = (
        db.query(models.TournamentParticipant, models.User)
        .join(models.User, models.User.id == models.TournamentParticipant.user_id)
        .filter(models.TournamentParticipant.tournament_id == tournament.id)
        .order_by(models.User.username.asc())
        .all()
    )
    team_rows = (
        db.query(models.TournamentTeamParticipant, models.Team)
        .join(models.Team, models.Team.id == models.TournamentTeamParticipant.team_id)
        .filter(models.TournamentTeamParticipant.tournament_id == tournament.id)
        .order_by(models.Team.name.asc())
        .all()
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/admin_tournament_detail.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "admin_tournaments",
            "tournament": tournament,
            "individual_board": individual_board,
            "team_board": team_board,
            "participants": [user.username for participant, user in participant_rows],
            "teams": [team.name for registration, team in team_rows],
        },
    )
