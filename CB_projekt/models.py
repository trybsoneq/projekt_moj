from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Index
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

    solves = relationship("Solve", back_populates="user")
    instances = relationship("ChallengeInstance", back_populates="user")


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


class Solve(Base):
    __tablename__ = "solves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="solves")
    challenge = relationship("Challenge", back_populates="solves")


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
