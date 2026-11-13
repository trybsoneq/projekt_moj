from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
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

    solves = relationship("Solve", back_populates="challenge")


class Solve(Base):
    __tablename__ = "solves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="solves")
    challenge = relationship("Challenge", back_populates="solves")
