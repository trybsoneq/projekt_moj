from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime, Text, Index, Boolean, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    score = Column(Integer, default=0)
    role = Column(String(20), nullable=False, default="user", server_default="user")
    xp = Column(Integer, nullable=False, default=0, server_default="0")
    current_streak = Column(Integer, nullable=False, default=0, server_default="0")
    longest_streak = Column(Integer, nullable=False, default=0, server_default="0")
    last_solve_date = Column(Date, nullable=True)

    solves = relationship("Solve", back_populates="user")
    instances = relationship("ChallengeInstance", back_populates="user")
    submissions = relationship("Submission", back_populates="user")
    hint_unlocks = relationship("HintUnlock", back_populates="user", cascade="all, delete-orphan")
    achievement_unlocks = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")


class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    long_description = Column(Text, nullable=True)
    hint = Column(Text, nullable=True)
    category = Column(String, nullable=False)
    points = Column(Integer, nullable=False)
    flag = Column(String, nullable=False)
    external_url = Column(String, nullable=True)
    docker_template = Column(String(64), nullable=True)

    solves = relationship("Solve", back_populates="challenge")
    instances = relationship("ChallengeInstance", back_populates="challenge")
    submissions = relationship("Submission", back_populates="challenge")
    hints = relationship("ChallengeHint", back_populates="challenge", order_by="ChallengeHint.level", cascade="all, delete-orphan")


class Solve(Base):
    __tablename__ = "solves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("ux_solves_user_challenge", "user_id", "challenge_id", unique=True),
    )

    user = relationship("User", back_populates="solves")
    challenge = relationship("Challenge", back_populates="solves")



class Submission(Base):
    """A flag attempt. The submitted flag text is intentionally never stored."""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    is_correct = Column(Boolean, nullable=False, default=False, index=True)
    submitted_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="submissions")
    challenge = relationship("Challenge", back_populates="submissions")

    __table_args__ = (
        Index("ix_submissions_user_time", "user_id", "submitted_at"),
        Index("ix_submissions_challenge_result", "challenge_id", "is_correct"),
    )


class Achievement(Base):
    """A seeded platform achievement or badge definition."""
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String(16), nullable=False, default="🏅")
    category = Column(String(32), nullable=False, default="general")
    xp_reward = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    unlocks = relationship("UserAchievement", back_populates="achievement", cascade="all, delete-orphan")


class UserAchievement(Base):
    """An earned badge. Context and event keys make awards idempotent."""
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id", ondelete="SET NULL"), nullable=True, index=True)
    context_key = Column(String(100), nullable=False, default="global", server_default="global")
    event_key = Column(String(150), nullable=True, unique=True)
    awarded_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    xp_awarded = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="achievement_unlocks")
    achievement = relationship("Achievement", back_populates="unlocks")
    challenge = relationship("Challenge")

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", "context_key", name="uq_user_achievement_context"),
        Index("ix_user_achievements_user_date", "user_id", "awarded_at"),
    )


class ChallengeHint(Base):
    """One of up to three ordered hints for a challenge."""
    __tablename__ = "challenge_hints"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    penalty_points = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    challenge = relationship("Challenge", back_populates="hints")
    unlocks = relationship("HintUnlock", back_populates="hint", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("challenge_id", "level", name="uq_challenge_hint_level"),
        CheckConstraint("level >= 1 AND level <= 3", name="ck_challenge_hint_level"),
        CheckConstraint("penalty_points >= 0", name="ck_challenge_hint_penalty"),
    )


class HintUnlock(Base):
    """A user unlocking a hint. Snapshot preserves the text they paid for."""
    __tablename__ = "hint_unlocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hint_id = Column(Integer, ForeignKey("challenge_hints.id", ondelete="CASCADE"), nullable=False, index=True)
    unlocked_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    points_deducted = Column(Integer, nullable=False, default=0)
    hint_content_snapshot = Column(Text, nullable=False)

    user = relationship("User", back_populates="hint_unlocks")
    hint = relationship("ChallengeHint", back_populates="unlocks")

    __table_args__ = (
        UniqueConstraint("user_id", "hint_id", name="uq_user_hint_unlock"),
        CheckConstraint("points_deducted >= 0", name="ck_hint_unlock_penalty"),
    )


class ChallengeInstance(Base):
    """One isolated Docker container assigned to one user and one challenge."""
    __tablename__ = "challenge_instances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    container_id = Column(String(128), unique=True, nullable=True)
    network_id = Column(String(128), nullable=True)  # private, internal challenge network
    proxy_container_id = Column(String(128), unique=True, nullable=True)
    ingress_network_id = Column(String(128), nullable=True)
    host_port = Column(Integer, nullable=True)  # published port of the trusted proxy
    status = Column(String(24), nullable=False, default="starting", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    stopped_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    user = relationship("User", back_populates="instances")
    challenge = relationship("Challenge", back_populates="instances")

    __table_args__ = (
        Index("ix_challenge_instances_user_status", "user_id", "status"),
        Index("ix_challenge_instances_expiry", "status", "expires_at"),
    )


# Register team and tournament tables on the shared SQLAlchemy metadata.
from tournament_models import (  # noqa: F401,E402
    Team, TeamMember, TeamInvitation, Tournament, TournamentChallenge,
    TournamentParticipant, TournamentTeamParticipant, TournamentSolve,
)
