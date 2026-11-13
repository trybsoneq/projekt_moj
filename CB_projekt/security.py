"""Uwierzytelnianie i autoryzacja platformy CTF.

Sesja jest podpisywana przez itsdangerous. W ciasteczku przechowujemy wyłącznie
identyfikator użytkownika, a rolę każdorazowo pobieramy z bazy danych.
"""
from __future__ import annotations

import os
import secrets
import warnings
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
        samesite="lax",
    )
