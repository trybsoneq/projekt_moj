"""Web routes for user-owned challenge instances."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from docker_manager import DockerManagerError, start_or_get_instance, stop_instance
from security import get_current_user, require_user

router = APIRouter()


@router.post("/challenge/{challenge_id}/instance/start")
def start_challenge_instance(
    challenge_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(
            url="/login?error=Zaloguj%20si%C4%99%2C%20aby%20uruchomi%C4%87%20%C5%9Brodowisko.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if challenge is None:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje.")
    try:
        start_or_get_instance(db, current_user, challenge)
    except DockerManagerError as exc:
        return RedirectResponse(
            url=f"/challenge/{challenge_id}?instance_error={quote(str(exc))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/challenge/{challenge_id}?instance_started=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/instance/{instance_id}/stop")
def stop_challenge_instance(
    instance_id: int,
    current_user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    instance = db.query(models.ChallengeInstance).filter(models.ChallengeInstance.id == instance_id).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="Instancja nie istnieje.")
    if instance.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nie możesz zatrzymać cudzego środowiska.")
    challenge_id = instance.challenge_id
    try:
        stop_instance(db, instance)
    except DockerManagerError as exc:
        return RedirectResponse(
            url=f"/challenge/{challenge_id}?instance_error={quote(str(exc))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/challenge/{challenge_id}?instance_stopped=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
