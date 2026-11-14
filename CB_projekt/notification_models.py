"""Persistent in-app notifications, preferences and announcements."""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from database import Base
import datetime


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(24), nullable=False, index=True)
    title = Column(String(140), nullable=False)
    body = Column(Text, nullable=False)
    target_url = Column(String(255), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    dedupe_key = Column(String(180), nullable=True, unique=True)
    announcement_id = Column(
        Integer,
        ForeignKey("announcements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("ix_notifications_user_read_date", "user_id", "is_read", "created_at"),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    team_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    tournament_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    achievement_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    announcement_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(140), nullable=False)
    body = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    sent_at = Column(DateTime, nullable=True)


class NotificationDispatch(Base):
    """Unique keys make scheduled and broadcast notifications idempotent."""
    __tablename__ = "notification_dispatches"

    id = Column(Integer, primary_key=True, index=True)
    event_key = Column(String(180), nullable=False, unique=True, index=True)
    dispatched_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
