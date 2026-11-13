"""User activity profile and administrator submission analytics."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

import models
from database import get_db
from security import require_admin, require_user
from achievement_service import level_from_xp

router = APIRouter()


@router.get("/profile")
def show_user_profile(
    request: Request,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    total_challenges = db.query(func.count(models.Challenge.id)).scalar() or 0
    solved_count = (
        db.query(func.count(models.Solve.id))
        .filter(models.Solve.user_id == current_user.id)
        .scalar()
        or 0
    )
    attempts_count = (
        db.query(func.count(models.Submission.id))
        .filter(models.Submission.user_id == current_user.id)
        .scalar()
        or 0
    )
    correct_count = (
        db.query(func.count(models.Submission.id))
        .filter(
            models.Submission.user_id == current_user.id,
            models.Submission.is_correct.is_(True),
        )
        .scalar()
        or 0
    )
    incorrect_count = attempts_count - correct_count
    accuracy = round((correct_count / attempts_count) * 100, 1) if attempts_count else 0.0
    progress = round((solved_count / total_challenges) * 100, 1) if total_challenges else 0.0

    recent_submissions = (
        db.query(models.Submission)
        .filter(models.Submission.user_id == current_user.id)
        .order_by(models.Submission.submitted_at.desc())
        .limit(50)
        .all()
    )
    category_rows = (
        db.query(models.Challenge.category, func.count(models.Solve.id))
        .join(models.Solve, models.Solve.challenge_id == models.Challenge.id)
        .filter(models.Solve.user_id == current_user.id)
        .group_by(models.Challenge.category)
        .order_by(func.count(models.Solve.id).desc())
        .all()
    )
    category_progress = [
        {"category": category, "solved": count}
        for category, count in category_rows
    ]

    level_info = level_from_xp(current_user.xp)
    earned_rows = (
        db.query(models.UserAchievement)
        .join(models.Achievement)
        .filter(models.UserAchievement.user_id == current_user.id)
        .order_by(models.UserAchievement.awarded_at.desc())
        .all()
    )
    earned_achievements = [
        {
            "name": row.achievement.name,
            "description": row.achievement.description,
            "icon": row.achievement.icon,
            "category": row.achievement.category,
            "xp_awarded": row.xp_awarded,
            "awarded_at": row.awarded_at,
            "challenge_title": row.challenge.title if row.challenge else None,
        }
        for row in earned_rows
    ]
    earned_codes = {row.achievement.code for row in earned_rows}
    available_achievements = (
        db.query(models.Achievement)
        .filter(models.Achievement.is_active.is_(True))
        .order_by(models.Achievement.category.asc(), models.Achievement.name.asc())
        .all()
    )
    locked_achievements = [
        {
            "name": badge.name,
            "description": badge.description,
            "icon": badge.icon,
            "category": badge.category,
            "xp_reward": badge.xp_reward,
        }
        for badge in available_achievements
        if badge.code not in earned_codes
    ]

    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/profile.html",
        {
            "request": request,
            "username": current_user.username,
            "is_admin": current_user.role == "admin",
            "user_points": current_user.score or 0,
            "active_page": "profile",
            "total_challenges": total_challenges,
            "solved_count": solved_count,
            "attempts_count": attempts_count,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "accuracy": accuracy,
            "progress": progress,
            "recent_submissions": recent_submissions,
            "category_progress": category_progress,
            "xp": current_user.xp or 0,
            "level_info": level_info,
            "current_streak": current_user.current_streak or 0,
            "longest_streak": current_user.longest_streak or 0,
            "last_solve_date": current_user.last_solve_date,
            "earned_achievements": earned_achievements,
            "locked_achievements": locked_achievements,
        },
    )


@router.get("/admin/activity")
def show_admin_activity(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_attempts = db.query(func.count(models.Submission.id)).scalar() or 0
    correct_attempts = (
        db.query(func.count(models.Submission.id))
        .filter(models.Submission.is_correct.is_(True))
        .scalar()
        or 0
    )
    incorrect_attempts = total_attempts - correct_attempts
    active_users = (
        db.query(func.count(func.distinct(models.Submission.user_id)))
        .scalar()
        or 0
    )

    submission_rows = (
        db.query(
            models.Submission.challenge_id,
            func.count(models.Submission.id).label("attempts"),
            func.coalesce(
                func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
                0,
            ).label("correct"),
        )
        .group_by(models.Submission.challenge_id)
        .all()
    )
    submission_map = {
        challenge_id: {"attempts": attempts, "correct": correct}
        for challenge_id, attempts, correct in submission_rows
    }

    solve_rows = (
        db.query(models.Solve.challenge_id, func.count(models.Solve.id))
        .group_by(models.Solve.challenge_id)
        .all()
    )
    solve_map = {challenge_id: count for challenge_id, count in solve_rows}

    challenge_analytics = []
    for challenge in db.query(models.Challenge).order_by(models.Challenge.title.asc()).all():
        submission_stats = submission_map.get(challenge.id, {"attempts": 0, "correct": 0})
        attempts = submission_stats["attempts"]
        correct = submission_stats["correct"]
        solve_count = solve_map.get(challenge.id, 0)
        challenge_analytics.append({
            "challenge": challenge,
            "attempts": attempts,
            "correct": correct,
            "incorrect": attempts - correct,
            "solves": solve_count,
            "success_rate": round((correct / attempts) * 100, 1) if attempts else 0.0,
        })

    user_rows = (
        db.query(
            models.User.username,
            models.User.score,
            func.count(models.Submission.id).label("attempts"),
            func.coalesce(
                func.sum(case((models.Submission.is_correct.is_(True), 1), else_=0)),
                0,
            ).label("correct"),
        )
        .outerjoin(models.Submission, models.Submission.user_id == models.User.id)
        .group_by(models.User.id)
        .order_by(models.User.score.desc(), models.User.username.asc())
        .limit(25)
        .all()
    )
    user_analytics = [
        {
            "username": username,
            "score": score or 0,
            "attempts": attempts,
            "correct": correct,
            "incorrect": attempts - correct,
        }
        for username, score, attempts, correct in user_rows
    ]

    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/admin_activity.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "admin_activity",
            "total_attempts": total_attempts,
            "correct_attempts": correct_attempts,
            "incorrect_attempts": incorrect_attempts,
            "active_users": active_users,
            "challenge_analytics": challenge_analytics,
            "user_analytics": user_analytics,
        },
    )
