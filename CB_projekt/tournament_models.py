"""Database models for teams and competitive CTF tournaments."""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String,
    Text, UniqueConstraint, Index,
)
from database import Base
import datetime


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    invite_code = Column(String(40), nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    role = Column(String(20), nullable=False, default="member")
    joined_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        CheckConstraint("role IN ('leader', 'member')", name="ck_team_member_role"),
    )


class TeamInvitation(Base):
    __tablename__ = "team_invitations"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="ck_team_invitation_status"),
        Index("ix_team_invites_user_status", "invited_user_id", "status"),
    )


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    competition_type = Column(String(20), nullable=False, default="individual")
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    max_participants = Column(Integer, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("competition_type IN ('individual', 'team')", name="ck_tournament_type"),
        CheckConstraint("status IN ('draft', 'open', 'finished')", name="ck_tournament_status"),
        CheckConstraint("max_participants IS NULL OR max_participants > 0", name="ck_tournament_capacity"),
        CheckConstraint("ends_at > starts_at", name="ck_tournament_dates"),
    )


class TournamentChallenge(Base):
    __tablename__ = "tournament_challenges"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    points = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tournament_id", "challenge_id", name="uq_tournament_challenge"),
        CheckConstraint("points >= 0", name="ck_tournament_challenge_points"),
    )


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tournament_id", "user_id", name="uq_tournament_user"),
    )


class TournamentTeamParticipant(Base):
    __tablename__ = "tournament_team_participants"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tournament_id", "team_id", name="uq_tournament_team"),
    )


class TournamentSolve(Base):
    """A credited tournament solve; individual and team scores remain separate from User.score."""
    __tablename__ = "tournament_solves"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    # In individual events team_id is NULL. In team events both fields are set:
    # user_id identifies the solver for the individual table; team_id credits the team.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    solver_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    points = Column(Integer, nullable=False)
    solved_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("tournament_id", "challenge_id", "user_id", name="uq_tournament_user_solve"),
        UniqueConstraint("tournament_id", "challenge_id", "team_id", name="uq_tournament_team_solve"),
        CheckConstraint("points >= 0", name="ck_tournament_solve_points"),
        Index("ix_tournament_solves_user", "tournament_id", "user_id"),
        Index("ix_tournament_solves_team", "tournament_id", "team_id"),
    )
