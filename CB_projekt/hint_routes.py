"""Protected endpoint for unlocking an ordered challenge hint."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from hint_service import HintError, unlock_hint
from security import require_user

router = APIRouter()


@router.post("/challenge/{challenge_id}/hint/{hint_id}/unlock")
def unlock_challenge_hint(
    challenge_id: int,
    hint_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    challenge = (
        db.query(models.Challenge)
        .filter(models.Challenge.id == challenge_id)
        .first()
    )
    if challenge is None:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje.")

    try:
        result = unlock_hint(db, current_user, challenge, hint_id)
    except HintError as exc:
        return RedirectResponse(
            url=f"/challenge/{challenge_id}?hint_error={quote(str(exc))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/challenge/{challenge_id}?hint_notice={quote(result['message'])}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
