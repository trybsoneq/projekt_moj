# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
import os
import asyncio
import logging
from urllib.parse import quote, urlsplit
from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session, joinedload
from database import engine, Base, get_db, SessionLocal
from migrate_roles import migrate as migrate_roles
import models

from passlib.context import CryptContext
from security import (
    get_current_user, require_admin, set_session_cookie, clear_session_cookie,
    auth_rate_limiter, client_rate_limit_key, validate_registration,
)
from docker_manager import (
    CLEANUP_INTERVAL_SECONDS,
    cleanup_expired_instances,
    get_active_instance,
    instance_url,
    is_supported_template,
    stop_instance,
)
from instance_routes import router as instance_router
from infrastructure_routes import router as infrastructure_router
from migrate_docker import migrate as migrate_docker
from migrate_activity import migrate as migrate_activity
from migrate_hints import migrate as migrate_hints
from migrate_achievements import migrate as migrate_achievements
from migrate_tournaments import migrate as migrate_tournaments
from migrate_notifications import migrate as migrate_notifications
from migrate_stage10 import migrate as migrate_stage10
from hint_routes import router as hint_router
from hint_service import HintError, get_hint_view, save_challenge_hints
from activity_routes import router as activity_router
from tournament_routes import router as tournament_router
from notification_routes import router as notification_router
from notification_service import process_due_tournament_notifications
from analytics_routes import router as analytics_router
from csrf_middleware import CSRFSecurityMiddleware
from activity_service import (
    MAX_FLAG_ATTEMPTS_PER_MINUTE,
    SubmissionRateLimitError,
    record_flag_submission,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

app = FastAPI(debug=False, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CSRFSecurityMiddleware)
app.include_router(instance_router)
app.include_router(infrastructure_router)
app.include_router(activity_router)
app.include_router(hint_router)
app.include_router(tournament_router)
app.include_router(notification_router)
app.include_router(analytics_router)
logger = logging.getLogger(__name__)

NOTIFICATION_POLL_INTERVAL_SECONDS = 60


@app.middleware("http")
async def load_unread_notification_count(request: Request, call_next):
    """Expose the signed-in user's unread count to the shared navigation."""
    request.state.unread_notification_count = 0
    if not request.url.path.startswith(("/assets/", "/images/")):
        token = request.cookies.get("ctf_session")
        if token:
            db = SessionLocal()
            try:
                current_user = get_current_user(request, db, token)
                if current_user:
                    request.state.unread_notification_count = (
                        db.query(models.Notification)
                        .filter(
                            models.Notification.user_id == current_user.id,
                            models.Notification.is_read.is_(False),
                        )
                        .count()
                    )
            except Exception:
                logger.exception("Nie udało się pobrać licznika powiadomień.")
            finally:
                db.close()
    return await call_next(request)

@app.exception_handler(Exception)
async def safe_unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(
        "Nieobsłużony wyjątek HTTP podczas obsługi %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Wystąpił nieoczekiwany błąd serwera. Spróbuj ponownie później."},
    )


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ZEROFOUR_DIR = os.path.join(TEMPLATES_DIR, "zerofour")

app.mount("/assets", StaticFiles(directory=os.path.join(ZEROFOUR_DIR, "assets")), name="assets")
app.mount("/images", StaticFiles(directory=os.path.join(ZEROFOUR_DIR, "images")), name="images")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.state.templates = templates


def init_database():
    db = SessionLocal()
    try:
        if db.query(models.Challenge).count() == 0:
            zadania = [
                models.Challenge(
                    title="Tajemniczy plik",
                    description="Znajdź flagę ukrytą w tym pliku tekstowym.",
                    long_description="Podczas rutynowego audytu wewnętrznego jeden z pracowników działu IT natknął się na podejrzany plik tekstowy. Twierdzi, że znajduje się w nim coś, co może być kluczem do głębszego problemu, ale nie jest w stanie tego zweryfikować. Plik wygląda jak zwykły raport, ale coś jest w nim nie tak... Może to tylko przeoczenie, a może celowo ukryta informacja? Twoim zadaniem jest dokładne przeanalizowanie tego pliku i znalezienie flagi.",
                    hint="Pamiętaj, że poszukiwana flaga jest zaszyfrowana.",
                    category="Forensics",
                    points=50,
                    flag="CTF{flaga_pliku_flag.txt}",
                    external_url=None
                ),
                models.Challenge(
                    title="Szyfr Cezara",
                    description="Odszyfruj zaszyfrowaną wiadomość.",
                    long_description="Juliusz Cezar używał tego szyfru do komunikacji ze swoimi generałami. Polega on na przesunięciu każdej litery w alfabecie o stałą liczbę miejsc. Zaszyfrowana wiadomość: egact wq jgólxua. Twoim zadaniem jest odszyfrowanie tej wiadomości i znalezienie flagi. Flaga ma format: CTF{odszyfrowana_wiadomosc} (małymi literami, spacje zastąp podkreślnikami).",
                    hint="Kluczem do tego zadania jest liczba 3.",
                    category="Cryptography",
                    points=100,
                    flag="CTF{cezar_to_geniusz}",
                    external_url=None
                ),
                models.Challenge(
                    title="Podatna wyszukiwarka",
                    description="Znajdź lukę w wyszukiwarce produktów i zdobądź flagę.",
                    long_description="Firma CyberShop uruchomiła właśnie swoją nową platformę e-commerce. Niestety, ktoś zapomniał o zabezpieczeniach... Wyszukiwarka produktów jest podatna na SQL Injection. Twoim zadaniem jest ominięcie zabezpieczeń i wyświetlenie wszystkich produktów, w tym ukrytego, który zawiera flagę.",
                    hint="Spróbuj wpisać coś w pole wyszukiwania, co sprawi, że baza danych pokaże wszystkie wpisy.",
                    category="Web Exploitation",
                    points=150,
                    flag="CTF{sql_injection_master}",
                    external_url=None,
                    docker_template="web_sqli"
                )
            ]
            db.add_all(zadania)
            db.commit()
            logger.info("Dodano zadania początkowe.")
        else:
            logger.info("Zadania już istnieją — pomijam inicjalizację.")
        
        user_count = db.query(models.User).count()
        logger.info("Liczba użytkowników w bazie: %s", user_count)
        
    except Exception:
        logger.exception("Błąd inicjalizacji bazy danych.")
    finally:
        db.close()

migrate_roles()
migrate_docker()
migrate_activity()
init_database()
migrate_hints()
migrate_achievements()
migrate_tournaments()
migrate_notifications()
migrate_stage10()


async def _instance_cleanup_worker():
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_instances)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Błąd okresowego sprzątania instancji Docker")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def _process_due_notifications():
    db = SessionLocal()
    try:
        process_due_tournament_notifications(db)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Błąd przetwarzania zaplanowanych powiadomień.")
    finally:
        db.close()


async def _notification_worker():
    while True:
        try:
            await asyncio.to_thread(_process_due_notifications)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Błąd cyklicznej obsługi powiadomień.")
        await asyncio.sleep(NOTIFICATION_POLL_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_background_workers():
    app.state.instance_cleanup_task = asyncio.create_task(_instance_cleanup_worker())
    app.state.notification_task = asyncio.create_task(_notification_worker())


@app.on_event("shutdown")
async def stop_background_workers():
    for task_name in ("instance_cleanup_task", "notification_task"):
        task = getattr(app.state, task_name, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def get_user_points(db: Session, user):
    return user.score if user is not None else 0


@app.get("/")
def home(
    request: Request, 
    current_user: models.User = Depends(get_current_user), 
    category: str = None,
    db: Session = Depends(get_db)
):
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    
    # Filtruj zadania jeśli wybrano kategorię
    query = db.query(models.Challenge)
    if category:
        query = query.filter(models.Challenge.category == category)
    all_challenges = query.all()
    
    return templates.TemplateResponse(
        request, 
        "zerofour/index.html", 
        {
            "request": request, 
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "challenges": all_challenges,
            "user_points": user_points,
            "active_page": "home",
            "selected_category": category
        }
    )

@app.get("/register")
def show_register_form(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    error = request.query_params.get("error")
    success = request.query_params.get("success")
    return templates.TemplateResponse(
        request, 
        "zerofour/register.html", 
        {
            "request": request, 
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"), 
            "user_points": user_points, 
            "error": error, 
            "success": success,
            "active_page": "register"
        }
    )

@app.post("/register")
def register_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    rate_key = f"register:{client_rate_limit_key(request)}"
    retry_after = auth_rate_limiter.check(rate_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Zbyt wiele prób rejestracji. Spróbuj ponownie później.",
            headers={"Retry-After": str(retry_after)},
        )

    username = (username or "").strip()
    validation_error = validate_registration(username, password, confirm_password)
    if validation_error:
        return RedirectResponse(
            url="/register?error=" + quote(validation_error),
            status_code=status.HTTP_302_FOUND,
        )

    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return RedirectResponse(
            url="/register?error=" + quote("Nazwa użytkownika jest już zajęta!"),
            status_code=status.HTTP_302_FOUND,
        )

    new_user = models.User(
        username=username,
        password_hash=get_password_hash(password),
        role="user",
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            url="/register?error=" + quote("Nazwa użytkownika jest już zajęta!"),
            status_code=status.HTTP_302_FOUND,
        )

    logger.info("Utworzono konto użytkownika: %s", username)
    return RedirectResponse(
        url="/login?success=" + quote("Konto utworzone! Możesz się zalogować."),
        status_code=status.HTTP_302_FOUND,
    )

@app.get("/login")
def show_login_form(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        request, 
        "zerofour/login.html", 
        {
            "request": request, 
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"), 
            "user_points": user_points, 
            "error": error,
            "active_page": "login"
        }
    )

@app.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    rate_key = f"login:{client_rate_limit_key(request)}"
    retry_after = auth_rate_limiter.check(rate_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Zbyt wiele nieudanych prób logowania. Spróbuj ponownie później.",
            headers={"Retry-After": str(retry_after)},
        )

    username = (username or "").strip()
    user = db.query(models.User).filter(models.User.username == username).first()
    try:
        valid_password = bool(user and verify_password(password, user.password_hash))
    except (ValueError, TypeError):
        valid_password = False
    if not valid_password:
        # The message is intentionally identical for unknown users and wrong passwords.
        return RedirectResponse(
            url="/login?error=" + quote("Nieprawidłowy login lub hasło!"),
            status_code=status.HTTP_302_FOUND,
        )

    auth_rate_limiter.reset(rate_key)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, user)
    logger.info("Użytkownik zalogował się poprawnie: %s", user.username)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(response)
    return response

@app.get("/admin")
def show_admin_panel(request: Request, current_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    current_user = current_admin
    all_challenges = (
        db.query(models.Challenge)
        .options(joinedload(models.Challenge.hints))
        .order_by(models.Challenge.title.asc())
        .all()
    )
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    
    return templates.TemplateResponse(
        request, 
        "zerofour/admin.html", 
        {
            "request": request, 
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"), 
            "challenges": all_challenges, 
            "user_points": user_points,
            "active_page": "admin"
        }
    )

def _validate_challenge_payload(
    title: str,
    description: str,
    category: str,
    points: int,
    flag: str,
    external_url: str | None,
) -> str | None:
    title = (title or "").strip()
    description = (description or "").strip()
    flag = (flag or "").strip()
    category = (category or "").strip()
    if not 3 <= len(title) <= 120:
        return "Tytuł zadania musi mieć od 3 do 120 znaków."
    if not 3 <= len(description) <= 2000:
        return "Opis zadania musi mieć od 3 do 2000 znaków."
    if category not in {"Web Exploitation", "Cryptography", "Forensics"}:
        return "Wybierz jedną z dostępnych kategorii zadań."
    if not 1 <= points <= 5000:
        return "Liczba punktów musi mieścić się w zakresie 1–5000."
    if not 3 <= len(flag) <= 255:
        return "Flaga musi mieć od 3 do 255 znaków."
    if external_url:
        value = external_url.strip()
        try:
            parsed = urlsplit(value)
            _ = parsed.port  # Accessing this property validates any explicit port.
            valid_url = (
                len(value) <= 500
                and not any(ord(character) < 32 for character in value)
                and parsed.scheme.lower() in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            return "Link zewnętrzny musi być poprawnym adresem HTTP lub HTTPS."
    return None


@app.post("/admin/add-challenge")
def add_challenge(
    title: str = Form(...),
    description: str = Form(...),
    long_description: str = Form(None),
    hint: str = Form(None),
    hint_1: str = Form(None),
    hint_1_penalty: int = Form(0),
    hint_2: str = Form(None),
    hint_2_penalty: int = Form(0),
    hint_3: str = Form(None),
    hint_3_penalty: int = Form(0),
    category: str = Form(...),
    points: int = Form(...),
    flag: str = Form(...),
    external_url: str = Form(None),
    docker_template: str = Form(""),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    docker_template = docker_template.strip() or None
    if not is_supported_template(docker_template):
        raise HTTPException(status_code=400, detail="Nieobsługiwany szablon Docker.")
    validation_error = _validate_challenge_payload(
        title, description, category, points, flag,
        None if docker_template else (external_url or "").strip() or None,
    )
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)
    title = title.strip()
    description = description.strip()
    flag = flag.strip()

    first_hint = (hint_1 or hint or "").strip()
    new_challenge = models.Challenge(
        title=title,
        description=description,
        long_description=long_description or description,
        hint=first_hint or None,
        category=category,
        points=points,
        flag=flag,
        external_url=None if docker_template else ((external_url or "").strip() or None),
        docker_template=docker_template
    )
    db.add(new_challenge)
    try:
        db.flush()
        save_challenge_hints(db, new_challenge, {
            1: (first_hint, hint_1_penalty),
            2: (hint_2, hint_2_penalty),
            3: (hint_3, hint_3_penalty),
        })
        db.commit()
    except HintError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.post("/admin/delete-challenge")
def delete_challenge(
    challenge_id: int = Form(...),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if challenge:
        has_history = any((
            db.query(models.Solve.id).filter(models.Solve.challenge_id == challenge_id).first(),
            db.query(models.Submission.id).filter(models.Submission.challenge_id == challenge_id).first(),
            db.query(models.TournamentChallenge.id).filter(models.TournamentChallenge.challenge_id == challenge_id).first(),
            db.query(models.TournamentSolve.id).filter(models.TournamentSolve.challenge_id == challenge_id).first(),
        ))
        if has_history:
            raise HTTPException(
                status_code=409,
                detail="Nie można usunąć zadania z historią prób, rozwiązań lub turniejów. Edytuj je zamiast usuwać.",
            )
        active_instances = db.query(models.ChallengeInstance).filter(
            models.ChallengeInstance.challenge_id == challenge_id,
            models.ChallengeInstance.status.in_(["starting", "running", "stop_failed"]),
        ).all()
        for instance in active_instances:
            stop_instance(db, instance)
        db.delete(challenge)
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.post("/admin/edit-challenge")
def edit_challenge(
    challenge_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    long_description: str = Form(None),
    hint: str = Form(None),
    hint_1: str = Form(None),
    hint_1_penalty: int = Form(0),
    hint_2: str = Form(None),
    hint_2_penalty: int = Form(0),
    hint_3: str = Form(None),
    hint_3_penalty: int = Form(0),
    category: str = Form(...),
    points: int = Form(...),
    flag: str = Form(...),
    external_url: str = Form(None),
    docker_template: str = Form(""),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    docker_template = docker_template.strip() or None
    if not is_supported_template(docker_template):
        raise HTTPException(status_code=400, detail="Nieobsługiwany szablon Docker.")
    validation_error = _validate_challenge_payload(
        title, description, category, points, flag,
        None if docker_template else (external_url or "").strip() or None,
    )
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if challenge is None:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje.")
    if challenge:
        title = title.strip()
        description = description.strip()
        flag = flag.strip()
        first_hint = (hint_1 or hint or "").strip()
        challenge.title = title
        challenge.description = description
        challenge.long_description = long_description or description
        challenge.hint = first_hint or None
        challenge.category = category
        challenge.points = points
        challenge.flag = flag
        challenge.docker_template = docker_template
        challenge.external_url = None if docker_template else (external_url.strip() or None)
        try:
            save_challenge_hints(db, challenge, {
                1: (first_hint, hint_1_penalty),
                2: (hint_2, hint_2_penalty),
                3: (hint_3, hint_3_penalty),
            })
            db.commit()
        except HintError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            db.rollback()
            raise
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.get("/scoreboard")
def show_scoreboard(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = (
        db.query(models.User)
        .order_by(models.User.score.desc(), models.User.username.asc())
        .limit(1000)
        .all()
    )
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    
    return templates.TemplateResponse(
        request,
        "zerofour/scoreboard.html",
        {
            "request": request,
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "users": users,
            "user_points": user_points,
            "active_page": "scoreboard"
        }
    )

@app.get("/rules")
def show_rules(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    return templates.TemplateResponse(
        request, 
        "zerofour/rules.html", 
        {
            "request": request, 
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"), 
            "user_points": user_points,
            "active_page": "rules"
        }
    )

@app.get("/challenge/{challenge_id}")
def show_challenge(request: Request, challenge_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje!")
    
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    active_instance = get_active_instance(db, current_user.id, challenge.id) if current_user else None
    current_instance_url = instance_url(active_instance) if active_instance else None
    instance_error = request.query_params.get("instance_error")
    instance_notice = request.query_params.get("instance_started") or request.query_params.get("instance_stopped")
    hint_message = request.query_params.get("hint_notice")
    hint_error = request.query_params.get("hint_error")
    hints = get_hint_view(db, challenge, current_user)
    challenge_attempts = 0
    if current_user:
        challenge_attempts = (
            db.query(models.Submission)
            .filter(
                models.Submission.user_id == current_user.id,
                models.Submission.challenge_id == challenge.id,
            )
            .count()
        )

    return templates.TemplateResponse(
        request,
        "zerofour/challenge.html",
        {
            "request": request,
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "challenge": challenge,
            "user_points": user_points,
            "current_instance": active_instance,
            "current_instance_url": current_instance_url,
            "instance_error": instance_error,
            "instance_notice": instance_notice,
            "challenge_attempts": challenge_attempts,
            "max_flag_attempts": MAX_FLAG_ATTEMPTS_PER_MINUTE,
            "hints": hints,
            "hint_message": hint_message,
            "hint_error": hint_error,
            "active_page": "home"
        }
    )

@app.get("/download/{challenge_id}")
def download_file(challenge_id: int):
    files_folder = os.path.join(BASE_DIR, "challenges_files")
    
    file_map = {
        1: "tajemniczy_plik.txt",
        2: "cezar.txt",
    }
    
    filename = file_map.get(challenge_id)
    if not filename:
        raise HTTPException(status_code=404, detail="Plik nie istnieje!")
    
    file_path = os.path.join(files_folder, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    
    raise HTTPException(status_code=404, detail="Plik nie istnieje!")

def _render_challenge_feedback(
    request: Request,
    challenge: models.Challenge,
    current_user: models.User | None,
    db: Session,
    message: str,
    solved: bool,
):
    logged_in_user = current_user.username if current_user else None
    active_instance = get_active_instance(db, current_user.id, challenge.id) if current_user else None
    current_instance_url = instance_url(active_instance) if active_instance else None
    challenge_attempts = 0
    if current_user:
        challenge_attempts = (
            db.query(models.Submission)
            .filter(
                models.Submission.user_id == current_user.id,
                models.Submission.challenge_id == challenge.id,
            )
            .count()
        )

    return templates.TemplateResponse(
        request,
        "zerofour/challenge.html",
        {
            "request": request,
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "challenge": challenge,
            "message": message,
            "solved": solved,
            "user_points": get_user_points(db, current_user),
            "current_instance": active_instance,
            "current_instance_url": current_instance_url,
            "instance_error": None,
            "instance_notice": None,
            "challenge_attempts": challenge_attempts,
            "max_flag_attempts": MAX_FLAG_ATTEMPTS_PER_MINUTE,
            "hints": get_hint_view(db, challenge, current_user),
            "hint_message": None,
            "hint_error": None,
            "active_page": "home",
        },
    )


@app.post("/challenge/{challenge_id}/check")
def check_flag(
    request: Request,
    challenge_id: int,
    flag: str = Form(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    challenge = (
        db.query(models.Challenge)
        .filter(models.Challenge.id == challenge_id)
        .first()
    )
    if challenge is None:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje!")

    if current_user is None:
        return _render_challenge_feedback(
            request,
            challenge,
            None,
            db,
            "Musisz być zalogowany, aby przesyłać flagi i zdobywać punkty.",
            False,
        )

    try:
        result = record_flag_submission(db, current_user, challenge, flag)
    except SubmissionRateLimitError as exc:
        return _render_challenge_feedback(
            request,
            challenge,
            current_user,
            db,
            str(exc),
            False,
        )

    if result["already_solved"]:
        tournament_points = result.get("tournament_points_awarded", 0)
        if tournament_points:
            message = (
                "Zadanie było już rozwiązane globalnie, ale zaliczono je do aktywnego turnieju! "
                f"+{tournament_points} pkt turniejowych."
            )
        else:
            message = "Już rozwiązałeś to zadanie!"
        solved = True
    elif result["is_correct"]:
        xp_gained = result.get("base_xp_awarded", 0) + result.get("bonus_xp_awarded", 0)
        message = (
            f"Poprawna flaga! +{result['points_awarded']} punktów, "
            f"+{xp_gained} XP. Osiągnięto poziom {result.get('level', 1)}."
        )
        awarded = result.get("achievements_awarded", [])
        if awarded:
            names = ", ".join(f"{item['icon']} {item['name']}" for item in awarded)
            message += f" Nowe osiągnięcia: {names}."
        if result.get("current_streak", 0):
            message += f" Seria rozwiązań: {result['current_streak']} dni."
        tournament_points = result.get("tournament_points_awarded", 0)
        if tournament_points:
            message += f" +{tournament_points} pkt turniejowych."
        solved = True
    else:
        message = "Niepoprawna flaga! Próba została zapisana w historii."
        solved = False

    return _render_challenge_feedback(
        request,
        challenge,
        current_user,
        db,
        message,
        solved,
    )
