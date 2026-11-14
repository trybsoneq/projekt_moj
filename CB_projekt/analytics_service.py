"""Read-only analytics for platform administrators, players and teams."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from sqlalchemy import case, func
from sqlalchemy.orm import Session

import models


def parse_date_range(
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[datetime | None, datetime | None, date | None, date | None]:
    """Parse inclusive calendar dates into a half-open UTC datetime range."""
    start_date = date.fromisoformat(date_from) if date_from else None
    end_date = date.fromisoformat(date_to) if date_to else None
    if start_date and end_date and start_date > end_date:
        raise ValueError("Data początkowa nie może być późniejsza niż końcowa.")
    start_at = datetime.combine(start_date, time.min) if start_date else None
    end_at = datetime.combine(end_date + timedelta(days=1), time.min) if end_date else None
    return start_at, end_at, start_date, end_date


def _apply_datetime_range(query, column, start_at, end_at):
    if start_at:
        query = query.filter(column >= start_at)
    if end_at:
        query = query.filter(column < end_at)
    return query


def _safe_rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _daily_rows(db: Session, start_at, end_at, days: int = 30) -> list[dict]:
    query = db.query(
        func.date(models.Submission.submitted_at).label("day"),
        func.count(models.Submission.id).label("attempts"),
        func.coalesce(
            func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
            0,
        ).label("correct"),
        func.count(func.distinct(models.Submission.user_id)).label("active_users"),
    )
    query = _apply_datetime_range(query, models.Submission.submitted_at, start_at, end_at)
    rows = query.group_by(func.date(models.Submission.submitted_at)).order_by(
        func.date(models.Submission.submitted_at).asc()
    ).all()
    if start_at is None and end_at is None:
        cutoff = (datetime.utcnow().date() - timedelta(days=days - 1)).isoformat()
        rows = [row for row in rows if str(row.day) >= cutoff]
    return [
        {
            "date": str(row.day),
            "attempts": int(row.attempts or 0),
            "correct": int(row.correct or 0),
            "active_users": int(row.active_users or 0),
        }
        for row in rows
    ]


def _user_daily_rows(db: Session, user_id: int, start_at, end_at) -> list[dict]:
    rows = (
        db.query(
            func.date(models.Submission.submitted_at).label("day"),
            func.count(models.Submission.id).label("attempts"),
            func.coalesce(
                func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
                0,
            ).label("correct"),
        )
        .filter(models.Submission.user_id == user_id)
        .filter(models.Submission.submitted_at >= start_at)
        .filter(models.Submission.submitted_at < end_at)
        .group_by(func.date(models.Submission.submitted_at))
        .order_by(func.date(models.Submission.submitted_at).asc())
        .all()
    )
    return [
        {
            "date": str(row.day),
            "attempts": int(row.attempts or 0),
            "correct": int(row.correct or 0),
            "active_users": 1,
        }
        for row in rows
    ]


def _challenge_rows(db: Session, start_at, end_at) -> list[dict]:
    submission_query = db.query(
        models.Submission.challenge_id.label("challenge_id"),
        func.count(models.Submission.id).label("attempts"),
        func.coalesce(
            func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
            0,
        ).label("correct"),
        func.count(func.distinct(models.Submission.user_id)).label("participants"),
    )
    submission_query = _apply_datetime_range(
        submission_query, models.Submission.submitted_at, start_at, end_at
    )
    submission_rows = submission_query.group_by(models.Submission.challenge_id).all()
    submission_map = {
        row.challenge_id: {
            "attempts": int(row.attempts or 0),
            "correct": int(row.correct or 0),
            "participants": int(row.participants or 0),
        }
        for row in submission_rows
    }

    solve_query = db.query(
        models.Solve.challenge_id,
        func.count(models.Solve.id).label("solves"),
        func.count(func.distinct(models.Solve.user_id)).label("solvers"),
    )
    solve_query = _apply_datetime_range(solve_query, models.Solve.timestamp, start_at, end_at)
    solve_map = {
        row.challenge_id: {"solves": int(row.solves or 0), "solvers": int(row.solvers or 0)}
        for row in solve_query.group_by(models.Solve.challenge_id).all()
    }

    rows = []
    challenges = db.query(models.Challenge).order_by(models.Challenge.title.asc()).all()
    for challenge in challenges:
        attempts = submission_map.get(challenge.id, {})
        solves = solve_map.get(challenge.id, {})
        rows.append({
            "id": challenge.id,
            "title": challenge.title,
            "category": challenge.category,
            "points": int(challenge.points or 0),
            "attempts": attempts.get("attempts", 0),
            "correct_attempts": attempts.get("correct", 0),
            "incorrect_attempts": attempts.get("attempts", 0) - attempts.get("correct", 0),
            "participants": attempts.get("participants", 0),
            "solves": solves.get("solvers", 0),
            "solve_events": solves.get("solves", 0),
            "success_rate": _safe_rate(
                attempts.get("correct", 0),
                attempts.get("attempts", 0),
            ),
        })
    rows.sort(key=lambda row: (-row["attempts"], -row["solves"], row["title"].casefold()))
    return rows


def _category_rows(db: Session, start_at, end_at) -> list[dict]:
    submission_query = db.query(
        models.Challenge.category.label("category"),
        func.count(models.Submission.id).label("attempts"),
        func.coalesce(
            func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
            0,
        ).label("correct"),
        func.count(func.distinct(models.Submission.user_id)).label("participants"),
    ).join(
        models.Submission,
        models.Submission.challenge_id == models.Challenge.id,
    )
    submission_query = _apply_datetime_range(
        submission_query, models.Submission.submitted_at, start_at, end_at
    )
    submission_rows = submission_query.group_by(models.Challenge.category).all()

    solve_query = db.query(
        models.Challenge.category.label("category"),
        func.count(func.distinct(models.Solve.user_id)).label("solvers"),
    ).join(
        models.Solve,
        models.Solve.challenge_id == models.Challenge.id,
    )
    solve_query = _apply_datetime_range(
        solve_query, models.Solve.timestamp, start_at, end_at
    )
    solve_map = {
        row.category: int(row.solvers or 0)
        for row in solve_query.group_by(models.Challenge.category).all()
    }

    return [
        {
            "category": row.category or "Bez kategorii",
            "attempts": int(row.attempts or 0),
            "correct": int(row.correct or 0),
            "participants": int(row.participants or 0),
            "solvers": solve_map.get(row.category, 0),
            "success_rate": _safe_rate(int(row.correct or 0), int(row.attempts or 0)),
        }
        for row in submission_rows
    ]



def _top_users(db: Session, start_at, end_at, limit: int = 20) -> list[dict]:
    users = db.query(models.User).order_by(
        models.User.score.desc(), models.User.username.asc()
    ).limit(500).all()
    user_ids = [user.id for user in users]
    if not user_ids:
        return []

    submission_query = db.query(
        models.Submission.user_id,
        func.count(models.Submission.id).label("attempts"),
        func.coalesce(
            func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
            0,
        ).label("correct"),
    ).filter(models.Submission.user_id.in_(user_ids))
    submission_query = _apply_datetime_range(
        submission_query, models.Submission.submitted_at, start_at, end_at
    )
    submission_map = {
        row.user_id: {"attempts": int(row.attempts or 0), "correct": int(row.correct or 0)}
        for row in submission_query.group_by(models.Submission.user_id).all()
    }

    solve_query = db.query(
        models.Solve.user_id,
        func.count(func.distinct(models.Solve.challenge_id)).label("solves"),
    ).filter(models.Solve.user_id.in_(user_ids))
    solve_query = _apply_datetime_range(
        solve_query, models.Solve.timestamp, start_at, end_at
    )
    solve_map = {
        row.user_id: int(row.solves or 0)
        for row in solve_query.group_by(models.Solve.user_id).all()
    }

    result = []
    for user in users:
        stats = submission_map.get(user.id, {"attempts": 0, "correct": 0})
        result.append({
            "user_id": user.id,
            "username": user.username,
            "score": int(user.score or 0),
            "xp": int(user.xp or 0),
            "attempts": stats["attempts"],
            "correct": stats["correct"],
            "solves": solve_map.get(user.id, 0),
            "accuracy": _safe_rate(stats["correct"], stats["attempts"]),
        })
    return result[:limit]



def _team_rows(db: Session, start_at, end_at, limit: int = 20) -> list[dict]:
    teams = db.query(models.Team).order_by(models.Team.name.asc()).all()
    membership_counts = {
        team_id: int(count)
        for team_id, count in db.query(
            models.TeamMember.team_id,
            func.count(models.TeamMember.id),
        ).group_by(models.TeamMember.team_id).all()
    }
    solve_query = db.query(
        models.TournamentSolve.team_id,
        func.count(models.TournamentSolve.id).label("solve_events"),
        func.coalesce(func.sum(models.TournamentSolve.points), 0).label("points"),
        func.count(func.distinct(models.TournamentSolve.challenge_id)).label("challenges"),
    ).filter(models.TournamentSolve.team_id.isnot(None))
    solve_query = _apply_datetime_range(
        solve_query, models.TournamentSolve.solved_at, start_at, end_at
    )
    solve_stats = {
        row.team_id: {
            "solve_events": int(row.solve_events or 0),
            "points": int(row.points or 0),
            "challenges": int(row.challenges or 0),
        }
        for row in solve_query.group_by(models.TournamentSolve.team_id).all()
    }
    tournament_counts = {
        team_id: int(count)
        for team_id, count in db.query(
            models.TournamentTeamParticipant.team_id,
            func.count(models.TournamentTeamParticipant.id),
        ).group_by(models.TournamentTeamParticipant.team_id).all()
    }
    result = []
    for team in teams:
        stats = solve_stats.get(team.id, {})
        result.append({
            "team_id": team.id,
            "name": team.name,
            "members": membership_counts.get(team.id, 0),
            "tournaments": tournament_counts.get(team.id, 0),
            "solve_events": stats.get("solve_events", 0),
            "points": stats.get("points", 0),
            "challenges": stats.get("challenges", 0),
        })
    result.sort(key=lambda row: (-row["points"], -row["solve_events"], row["name"].casefold()))
    return result[:limit]


def _tournament_rows(db: Session, start_at, end_at) -> list[dict]:
    query = db.query(models.Tournament)
    query = _apply_datetime_range(query, models.Tournament.starts_at, start_at, end_at)
    tournaments = query.order_by(models.Tournament.starts_at.desc()).all()
    result = []
    for event in tournaments:
        if event.competition_type == "team":
            participants = db.query(models.TournamentTeamParticipant).filter_by(
                tournament_id=event.id
            ).count()
        else:
            participants = db.query(models.TournamentParticipant).filter_by(
                tournament_id=event.id
            ).count()
        points_query = db.query(
            func.coalesce(func.sum(models.TournamentSolve.points), 0)
        ).filter(models.TournamentSolve.tournament_id == event.id)
        points_query = _apply_datetime_range(
            points_query, models.TournamentSolve.solved_at, start_at, end_at
        )
        points = points_query.scalar() or 0
        result.append({
            "id": event.id,
            "title": event.title,
            "type": event.competition_type,
            "status": event.status,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "participants": participants,
            "points": int(points),
        })
    return result


def admin_analytics(
    db: Session,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict:
    total_users = db.query(func.count(models.User.id)).scalar() or 0
    total_challenges = db.query(func.count(models.Challenge.id)).scalar() or 0
    total_teams = db.query(func.count(models.Team.id)).scalar() or 0
    total_tournaments = db.query(func.count(models.Tournament.id)).scalar() or 0
    live_tournaments = db.query(func.count(models.Tournament.id)).filter(
        models.Tournament.status == "open"
    ).scalar() or 0

    submission_query = db.query(
        func.count(models.Submission.id),
        func.coalesce(
            func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
            0,
        ),
        func.count(func.distinct(models.Submission.user_id)),
    )
    submission_query = _apply_datetime_range(
        submission_query, models.Submission.submitted_at, start_at, end_at
    )
    attempts, correct, active_users = submission_query.one()
    attempts, correct, active_users = int(attempts or 0), int(correct or 0), int(active_users or 0)

    solve_query = db.query(func.count(models.Solve.id))
    solve_query = _apply_datetime_range(solve_query, models.Solve.timestamp, start_at, end_at)
    solves = int(solve_query.scalar() or 0)

    return {
        "total_users": int(total_users),
        "total_challenges": int(total_challenges),
        "total_teams": int(total_teams),
        "total_tournaments": int(total_tournaments),
        "live_tournaments": int(live_tournaments),
        "attempts": attempts,
        "correct_attempts": correct,
        "incorrect_attempts": attempts - correct,
        "active_users": active_users,
        "solves": solves,
        "success_rate": _safe_rate(correct, attempts),
        "daily": _daily_rows(db, start_at, end_at),
        "challenges": _challenge_rows(db, start_at, end_at),
        "categories": _category_rows(db, start_at, end_at),
        "top_users": _top_users(db, start_at, end_at),
        "teams": _team_rows(db, start_at, end_at),
        "tournaments": _tournament_rows(db, start_at, end_at),
    }


def player_analytics(db: Session, user: models.User) -> dict:
    attempts = db.query(func.count(models.Submission.id)).filter(
        models.Submission.user_id == user.id
    ).scalar() or 0
    correct = db.query(func.count(models.Submission.id)).filter(
        models.Submission.user_id == user.id,
        models.Submission.is_correct.is_(True),
    ).scalar() or 0
    solves = db.query(func.count(models.Solve.id)).filter(
        models.Solve.user_id == user.id
    ).scalar() or 0

    category_rows = (
        db.query(
            models.Challenge.category,
            func.count(models.Solve.id).label("solves"),
            func.count(models.Challenge.id).label("total"),
        )
        .outerjoin(
            models.Solve,
            (models.Solve.challenge_id == models.Challenge.id)
            & (models.Solve.user_id == user.id),
        )
        .group_by(models.Challenge.category)
        .order_by(models.Challenge.category.asc())
        .all()
    )
    categories = [
        {
            "category": row.category or "Bez kategorii",
            "solves": int(row.solves or 0),
            "total": int(row.total or 0),
            "progress": _safe_rate(int(row.solves or 0), int(row.total or 0)),
        }
        for row in category_rows
    ]

    recent_activity = _user_daily_rows(
        db,
        user.id,
        datetime.combine(datetime.utcnow().date() - timedelta(days=29), time.min),
        datetime.combine(datetime.utcnow().date() + timedelta(days=1), time.min),
    )
    user_tournaments = (
        db.query(models.TournamentParticipant, models.Tournament)
        .join(models.Tournament, models.Tournament.id == models.TournamentParticipant.tournament_id)
        .filter(models.TournamentParticipant.user_id == user.id)
        .order_by(models.Tournament.starts_at.desc())
        .all()
    )
    tournament_stats = []
    for participant, tournament in user_tournaments:
        own = db.query(
            func.count(models.TournamentSolve.id),
            func.coalesce(func.sum(models.TournamentSolve.points), 0),
        ).filter(
            models.TournamentSolve.tournament_id == tournament.id,
            models.TournamentSolve.user_id == user.id,
        ).one()
        tournament_stats.append({
            "id": tournament.id,
            "title": tournament.title,
            "status": tournament.status,
            "points": int(own[1] or 0),
            "solves": int(own[0] or 0),
        })

    return {
        "username": user.username,
        "score": int(user.score or 0),
        "xp": int(user.xp or 0),
        "level": (int(user.xp or 0) // 100) + 1,
        "current_streak": int(user.current_streak or 0),
        "longest_streak": int(user.longest_streak or 0),
        "attempts": int(attempts),
        "correct": int(correct),
        "incorrect": int(attempts) - int(correct),
        "solves": int(solves),
        "accuracy": _safe_rate(int(correct), int(attempts)),
        "categories": categories,
        "daily": recent_activity,
        "tournaments": tournament_stats,
    }


def team_analytics(db: Session, team: models.Team) -> dict:
    members = (
        db.query(models.TeamMember, models.User)
        .join(models.User, models.User.id == models.TeamMember.user_id)
        .filter(models.TeamMember.team_id == team.id)
        .order_by(models.TeamMember.role.desc(), models.User.username.asc())
        .all()
    )
    member_stats = []
    for membership, user in members:
        attempts = db.query(func.count(models.Submission.id)).filter(
            models.Submission.user_id == user.id
        ).scalar() or 0
        solves = db.query(func.count(models.Solve.id)).filter(
            models.Solve.user_id == user.id
        ).scalar() or 0
        tournament_points = db.query(
            func.coalesce(func.sum(models.TournamentSolve.points), 0)
        ).filter(
            models.TournamentSolve.team_id == team.id,
            models.TournamentSolve.solver_user_id == user.id,
        ).scalar() or 0
        member_stats.append({
            "username": user.username,
            "role": membership.role,
            "score": int(user.score or 0),
            "xp": int(user.xp or 0),
            "attempts": int(attempts),
            "solves": int(solves),
            "tournament_points": int(tournament_points),
        })

    tournament_rows = (
        db.query(models.TournamentTeamParticipant, models.Tournament)
        .join(models.Tournament, models.Tournament.id == models.TournamentTeamParticipant.tournament_id)
        .filter(models.TournamentTeamParticipant.team_id == team.id)
        .order_by(models.Tournament.starts_at.desc())
        .all()
    )
    tournament_stats = []
    for registration, tournament in tournament_rows:
        solve_count, points = db.query(
            func.count(models.TournamentSolve.id),
            func.coalesce(func.sum(models.TournamentSolve.points), 0),
        ).filter(
            models.TournamentSolve.tournament_id == tournament.id,
            models.TournamentSolve.team_id == team.id,
        ).one()
        tournament_stats.append({
            "id": tournament.id,
            "title": tournament.title,
            "status": tournament.status,
            "solves": int(solve_count or 0),
            "points": int(points or 0),
        })

    total_attempts = sum(row["attempts"] for row in member_stats)
    total_solves = sum(row["solves"] for row in member_stats)
    return {
        "team": team,
        "members": member_stats,
        "member_count": len(member_stats),
        "total_attempts": total_attempts,
        "total_solves": total_solves,
        "tournament_points": sum(row["points"] for row in tournament_stats),
        "tournaments": tournament_stats,
    }


def admin_report_rows(analytics: dict, kind: str) -> list[list[str]]:
    """Convert a selected report section into safe, flat CSV rows."""
    if kind == "summary":
        return [
            ["Metryka", "Wartość"],
            ["Użytkownicy", str(analytics["total_users"])],
            ["Zadania", str(analytics["total_challenges"])],
            ["Drużyny", str(analytics["total_teams"])],
            ["Turnieje", str(analytics["total_tournaments"])],
            ["Aktywne turnieje", str(analytics["live_tournaments"])],
            ["Aktywni użytkownicy w okresie", str(analytics["active_users"])],
            ["Próby flag", str(analytics["attempts"])],
            ["Poprawne próby", str(analytics["correct_attempts"])],
            ["Niepoprawne próby", str(analytics["incorrect_attempts"])],
            ["Rozwiązania", str(analytics["solves"])],
            ["Skuteczność (%)", str(analytics["success_rate"])],
        ]
    if kind == "challenges":
        return [["Zadanie", "Kategoria", "Punkty", "Próby", "Poprawne", "Niepoprawne", "Rozwiązujący", "Skuteczność (%)"]] + [
            [
                r["title"], r["category"], str(r["points"]), str(r["attempts"]),
                str(r["correct_attempts"]), str(r["incorrect_attempts"]),
                str(r["solves"]), str(r["success_rate"]),
            ]
            for r in analytics["challenges"]
        ]
    if kind == "users":
        return [["Użytkownik", "Punkty", "XP", "Próby", "Poprawne", "Rozwiązane", "Skuteczność (%)"]] + [
            [r["username"], str(r["score"]), str(r["xp"]), str(r["attempts"]), str(r["correct"]), str(r["solves"]), str(r["accuracy"])]
            for r in analytics["top_users"]
        ]
    if kind == "categories":
        return [["Kategoria", "Próby", "Poprawne", "Rozwiązujący", "Skuteczność (%)"]] + [
            [r["category"], str(r["attempts"]), str(r["correct"]), str(r["solvers"]), str(r["success_rate"])]
            for r in analytics["categories"]
        ]
    if kind == "daily":
        return [["Data UTC", "Próby", "Poprawne", "Aktywni użytkownicy"]] + [
            [r["date"], str(r["attempts"]), str(r["correct"]), str(r["active_users"])]
            for r in analytics["daily"]
        ]
    if kind == "teams":
        return [["Drużyna", "Członkowie", "Turnieje", "Rozwiązania turniejowe", "Punkty turniejowe"]] + [
            [r["name"], str(r["members"]), str(r["tournaments"]), str(r["solve_events"]), str(r["points"])]
            for r in analytics["teams"]
        ]
    if kind == "tournaments":
        return [["Turniej", "Tryb", "Status", "Start UTC", "Koniec UTC", "Uczestnicy", "Punkty"]] + [
            [
                r["title"], r["type"], r["status"],
                r["starts_at"].isoformat(sep=" "), r["ends_at"].isoformat(sep=" "),
                str(r["participants"]), str(r["points"]),
            ]
            for r in analytics["tournaments"]
        ]
    raise ValueError("Nieznany typ raportu.")
