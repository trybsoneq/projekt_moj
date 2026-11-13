"""Administrator infrastructure dashboard and protected lifecycle actions."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from docker_manager import (
    DockerManagerError,
    format_bytes,
    get_infrastructure_overview,
    restart_instance,
    stop_instance,
)
from security import require_admin

router = APIRouter()


def _dashboard_redirect(*, notice: str = "", error: str = ""):
    if notice:
        return RedirectResponse(
            url=f"/admin/infrastructure?notice={quote(notice)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/admin/infrastructure?error={quote(error)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/admin/infrastructure")
def show_infrastructure_dashboard(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = get_infrastructure_overview(db)
    return request.app.state.templates.TemplateResponse(
        request,
        "zerofour/infrastructure.html",
        {
            "request": request,
            "username": current_admin.username,
            "is_admin": True,
            "user_points": current_admin.score or 0,
            "active_page": "infrastructure",
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
            "format_bytes": format_bytes,
            **snapshot,
        },
    )


@router.post("/admin/infrastructure/{instance_id}/stop")
def admin_stop_instance(
    instance_id: int,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    instance = (
        db.query(models.ChallengeInstance)
        .filter(models.ChallengeInstance.id == instance_id)
        .first()
    )
    if instance is None:
        raise HTTPException(status_code=404, detail="Instancja nie istnieje.")
    try:
        stop_instance(db, instance)
    except DockerManagerError as exc:
        return _dashboard_redirect(error=str(exc))
    return _dashboard_redirect(notice=f"Instancja #{instance_id} została zatrzymana.")


@router.post("/admin/infrastructure/{instance_id}/restart")
def admin_restart_instance(
    instance_id: int,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    instance = (
        db.query(models.ChallengeInstance)
        .filter(models.ChallengeInstance.id == instance_id)
        .first()
    )
    if instance is None:
        raise HTTPException(status_code=404, detail="Instancja nie istnieje.")
    try:
        restart_instance(db, instance)
    except DockerManagerError as exc:
        return _dashboard_redirect(error=str(exc))
    return _dashboard_redirect(notice=f"Instancja #{instance_id} została uruchomiona ponownie.")
