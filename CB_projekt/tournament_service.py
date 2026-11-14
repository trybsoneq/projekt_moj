"""Registration, scoring and ranking logic for CTF tournaments."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session

import models


class TournamentError(ValueError):
    """A user-facing tournament operation is not allowed."""


def registered_count(db: Session, tournament: models.Tournament) -> int:
    if tournament.competition_type == "team":
        return (
            db.query(models.TournamentTeamParticipant)
            .filter(models.TournamentTeamParticipant.tournament_id == tournament.id)
            .count()
        )
    return (
        db.query(models.TournamentParticipant)
        .filter(models.TournamentParticipant.tournament_id == tournament.id)
        .count()
    )


def join_tournament(
    db: Session,
    user: models.User,
    tournament: models.Tournament,
    now: datetime | None = None,
) -> None:
    """Register a user or their team before the scheduled start."""
    now = now or datetime.utcnow()
    if tournament.status != "open":
        raise TournamentError("Zapisy do tego turnieju nie są otwarte.")
    if now >= tournament.starts_at:
        raise TournamentError("Zapisy zakończyły się wraz ze startem turnieju.")
    if now >= tournament.ends_at:
        raise TournamentError("Turniej już się zakończył.")

    if tournament.competition_type == "individual":
        existing = (
            db.query(models.TournamentParticipant)
            .filter_by(tournament_id=tournament.id, user_id=user.id)
            .first()
        )
        if existing:
            raise TournamentError("Jesteś już zapisany do tego turnieju.")
        if tournament.max_participants and registered_count(db, tournament) >= tournament.max_participants:
            raise TournamentError("Limit uczestników tego turnieju został osiągnięty.")
        db.add(models.TournamentParticipant(tournament_id=tournament.id, user_id=user.id))
        db.flush()
        return

    membership = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.user_id == user.id)
        .first()
    )
    if membership is None:
        raise TournamentError("Najpierw dołącz do drużyny lub ją utwórz.")
    if membership.role != "leader":
        raise TournamentError("Turniej drużynowy może zgłosić tylko lider drużyny.")

    existing = (
        db.query(models.TournamentTeamParticipant)
        .filter_by(tournament_id=tournament.id, team_id=membership.team_id)
        .first()
    )
    if existing:
        raise TournamentError("Twoja drużyna jest już zapisana do tego turnieju.")
    if tournament.max_participants and registered_count(db, tournament) >= tournament.max_participants:
        raise TournamentError("Limit drużyn tego turnieju został osiągnięty.")

    db.add(models.TournamentTeamParticipant(
        tournament_id=tournament.id,
        team_id=membership.team_id,
    ))
    # Snapshot the roster for the individual leaderboard as well.
    members = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.team_id == membership.team_id)
        .all()
    )
    for member in members:
        already_registered = (
            db.query(models.TournamentParticipant)
            .filter_by(tournament_id=tournament.id, user_id=member.user_id)
            .first()
        )
        if already_registered is None:
            db.add(models.TournamentParticipant(
                tournament_id=tournament.id,
                user_id=member.user_id,
            ))
    db.flush()


def record_tournament_solve(
    db: Session,
    user: models.User,
    challenge: models.Challenge,
    solved_at: datetime | None = None,
) -> int:
    """Credit the challenge in every eligible live tournament, without touching global score or XP."""
    solved_at = solved_at or datetime.utcnow()
    eligible = (
        db.query(models.Tournament, models.TournamentChallenge)
        .join(
            models.TournamentChallenge,
            models.TournamentChallenge.tournament_id == models.Tournament.id,
        )
        .filter(
            models.TournamentChallenge.challenge_id == challenge.id,
            models.Tournament.status == "open",
            models.Tournament.starts_at <= solved_at,
            models.Tournament.ends_at > solved_at,
        )
        .all()
    )

    awarded = 0
    for tournament, tournament_challenge in eligible:
        if tournament.competition_type == "individual":
            registered = (
                db.query(models.TournamentParticipant)
                .filter_by(tournament_id=tournament.id, user_id=user.id)
                .first()
            )
            if not registered:
                continue
            exists = (
                db.query(models.TournamentSolve)
                .filter_by(
                    tournament_id=tournament.id,
                    challenge_id=challenge.id,
                    user_id=user.id,
                )
                .first()
            )
            if exists:
                continue
            db.add(models.TournamentSolve(
                tournament_id=tournament.id,
                challenge_id=challenge.id,
                user_id=user.id,
                team_id=None,
                solver_user_id=user.id,
                points=tournament_challenge.points,
                solved_at=solved_at,
            ))
            awarded += tournament_challenge.points
            continue

        membership = (
            db.query(models.TeamMember)
            .filter(models.TeamMember.user_id == user.id)
            .first()
        )
        if membership is None:
            continue
        team_registration = (
            db.query(models.TournamentTeamParticipant)
            .filter_by(tournament_id=tournament.id, team_id=membership.team_id)
            .first()
        )
        if not team_registration:
            continue
        exists = (
            db.query(models.TournamentSolve)
            .filter_by(
                tournament_id=tournament.id,
                challenge_id=challenge.id,
                team_id=membership.team_id,
            )
            .first()
        )
        if exists:
            continue
        db.add(models.TournamentSolve(
            tournament_id=tournament.id,
            challenge_id=challenge.id,
            user_id=user.id,
            team_id=membership.team_id,
            solver_user_id=user.id,
            points=tournament_challenge.points,
            solved_at=solved_at,
        ))
        awarded += tournament_challenge.points

    db.flush()
    return awarded


def _rank_rows(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda row: (
        -row["points"],
        -row["solves"],
        row["last_solve"] or datetime.max,
        row["name"].casefold(),
    ))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def tournament_leaderboards(
    db: Session,
    tournament: models.Tournament,
) -> tuple[list[dict], list[dict]]:
    """Return individual standings and, for team events, team standings."""
    solves = (
        db.query(models.TournamentSolve)
        .filter(models.TournamentSolve.tournament_id == tournament.id)
        .all()
    )

    user_rows = (
        db.query(models.TournamentParticipant, models.User)
        .join(models.User, models.User.id == models.TournamentParticipant.user_id)
        .filter(models.TournamentParticipant.tournament_id == tournament.id)
        .all()
    )
    individual = []
    for participant, user in user_rows:
        own_solves = [row for row in solves if row.user_id == user.id]
        individual.append({
            "participant_id": user.id,
            "name": user.username,
            "points": sum(row.points for row in own_solves),
            "solves": len(own_solves),
            "last_solve": max((row.solved_at for row in own_solves), default=None),
        })
    _rank_rows(individual)

    teams = []
    if tournament.competition_type == "team":
        team_rows = (
            db.query(models.TournamentTeamParticipant, models.Team)
            .join(models.Team, models.Team.id == models.TournamentTeamParticipant.team_id)
            .filter(models.TournamentTeamParticipant.tournament_id == tournament.id)
            .all()
        )
        for participant, team in team_rows:
            team_solves = [row for row in solves if row.team_id == team.id]
            teams.append({
                "participant_id": team.id,
                "name": team.name,
                "points": sum(row.points for row in team_solves),
                "solves": len(team_solves),
                "last_solve": max((row.solved_at for row in team_solves), default=None),
            })
        _rank_rows(teams)

    return individual, teams
