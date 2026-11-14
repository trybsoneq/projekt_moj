"""Authentication, session handling and abuse protection for CyberSim."""
from __future__ import annotations

import os
import secrets
import threading
import time
import warnings
from collections import deque
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from database import get_db
import models

SESSION_COOKIE_NAME = "ctf_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
SESSION_SECRET = os.getenv("CTF_SECRET_KEY")

if not SESSION_SECRET:
    if os.getenv("CTF_ENV", "development").lower() == "production":
        raise RuntimeError("CTF_SECRET_KEY musi być ustawiony w środowisku produkcyjnym.")
    SESSION_SECRET = secrets.token_urlsafe(48)
    warnings.warn(
        "CTF_SECRET_KEY nie jest ustawiony; wygenerowano tymczasowy klucz. "
        "Ustaw własny klucz przed restartem lub wdrożeniem.",
        RuntimeWarning,
    )

if (
    os.getenv("CTF_ENV", "development").lower() == "production"
    and os.getenv("CTF_COOKIE_SECURE", "0") != "1"
):
    raise RuntimeError(
        "W środowisku produkcyjnym ustaw CTF_COOKIE_SECURE=1 i udostępniaj aplikację przez HTTPS."
    )

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="ctf-platform-session")


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": int(user_id)})


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Optional[models.User]:
    if not session_token:
        return None
    try:
        payload = _serializer.loads(session_token, max_age=SESSION_MAX_AGE_SECONDS)
        user_id = int(payload["user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_user(user: Optional[models.User] = Depends(get_current_user)) -> models.User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Zaloguj się, aby wykonać tę operację.",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


def require_admin(user: models.User = Depends(require_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Brak uprawnień. Ta operacja jest dostępna tylko dla administratora.",
        )
    return user


def set_session_cookie(response, user: models.User) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=os.getenv("CTF_COOKIE_SECURE", "0") == "1",
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=os.getenv("CTF_COOKIE_SECURE", "0") == "1",
        samesite="lax",
    )


class SlidingWindowRateLimiter:
    """Small per-process sliding-window limiter for authentication endpoints.

    For deployments with multiple application workers, enforce the same limit
    at the reverse proxy or use a shared limiter store.
    """

    def __init__(self, limit: int = 10, window_seconds: int = 900):
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> int:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - self.window_seconds
        normalized = (key or "unknown")[:160]
        with self._lock:
            events = self._events.setdefault(normalized, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return max(1, int(events[0] + self.window_seconds - current + 0.999))
            events.append(current)
            if len(self._events) > 10000:
                stale_keys = [item for item, values in self._events.items() if not values or values[-1] <= cutoff]
                for stale_key in stale_keys[:5000]:
                    self._events.pop(stale_key, None)
            return 0

    def reset(self, key: str) -> None:
        normalized = (key or "unknown")[:160]
        with self._lock:
            self._events.pop(normalized, None)


AUTH_RATE_LIMIT = max(1, int(os.getenv("CTF_AUTH_ATTEMPTS", "10")))
AUTH_RATE_WINDOW_SECONDS = max(60, int(os.getenv("CTF_AUTH_WINDOW_SECONDS", "900")))
auth_rate_limiter = SlidingWindowRateLimiter(AUTH_RATE_LIMIT, AUTH_RATE_WINDOW_SECONDS)


def client_rate_limit_key(request: Request) -> str:
    """Use the direct peer address; do not trust spoofable X-Forwarded-For headers."""
    return request.client.host if request.client and request.client.host else "unknown"


def validate_registration(username: str, password: str, confirmation: str) -> str | None:
    username = (username or "").strip()
    if not 3 <= len(username) <= 32:
        return "Nazwa użytkownika musi mieć od 3 do 32 znaków."
    if not all(character.isalnum() or character in "._-" for character in username):
        return "Nazwa użytkownika może zawierać tylko litery, cyfry oraz znaki . _ -."
    if len(password or "") < 10:
        return "Hasło musi mieć co najmniej 10 znaków."
    if len((password or "").encode("utf-8")) > 72:
        return "Hasło jest zbyt długie (maksymalnie 72 bajty w UTF-8)."
    if password != confirmation:
        return "Hasła nie są identyczne."
    return None
