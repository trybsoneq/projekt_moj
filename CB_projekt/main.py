# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
import os

from sqlalchemy.orm import Session
from database import engine, Base, get_db, SessionLocal
import models

from passlib.context import CryptContext
from security import get_current_user, require_admin, set_session_cookie, clear_session_cookie

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

if not os.path.exists("ctf_platform.db"):
    Base.metadata.create_all(bind=engine)
    print("Utworzono nowa baze danych")
else:
    print("Baza danych juz istnieje")
    Base.metadata.create_all(bind=engine)

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ZEROFOUR_DIR = os.path.join(TEMPLATES_DIR, "zerofour")

app.mount("/assets", StaticFiles(directory=os.path.join(ZEROFOUR_DIR, "assets")), name="assets")
app.mount("/images", StaticFiles(directory=os.path.join(ZEROFOUR_DIR, "images")), name="images")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
                    external_url="http://127.0.0.1:5000"
                )
            ]
            db.add_all(zadania)
            db.commit()
            print("Dodano zadania.")
        else:
            print("Zadania juz istnieja - pomijam.")
        
        user_count = db.query(models.User).count()
        print(f"Liczba uzytkownikow w bazie: {user_count}")
        
    except Exception as e:
        print(f"Blad inicjalizacji: {e}")
    finally:
        db.close()

init_database()


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
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    if len(password) < 6:
        return RedirectResponse(url="/register?error=Hasło musi mieć conajmniej 6 znaków!", status_code=status.HTTP_302_FOUND)
    
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return RedirectResponse(url="/register?error=Nazwa użytkownika jest już zajęta!", status_code=status.HTTP_302_FOUND)
    
    new_user = models.User(username=username, password_hash=get_password_hash(password), role="user")
    db.add(new_user)
    db.commit()
    
    return RedirectResponse(url="/login?success=Konto utworzone! Możesz się zalogować.", status_code=status.HTTP_302_FOUND)

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
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=Nieprawidłowy login lub hasło!", status_code=status.HTTP_302_FOUND)
    
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, user)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(response)
    return response

@app.get("/admin")
def show_admin_panel(request: Request, current_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    current_user = current_admin
    all_challenges = db.query(models.Challenge).all()
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

@app.post("/admin/add-challenge")
def add_challenge(
    title: str = Form(...),
    description: str = Form(...),
    long_description: str = Form(None),
    hint: str = Form(None),
    category: str = Form(...),
    points: int = Form(...),
    flag: str = Form(...),
    external_url: str = Form(None),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    new_challenge = models.Challenge(
        title=title,
        description=description,
        long_description=long_description or description,
        hint=hint,
        category=category,
        points=points,
        flag=flag,
        external_url=external_url
    )
    db.add(new_challenge)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.post("/admin/delete-challenge")
def delete_challenge(
    challenge_id: int = Form(...),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if challenge:
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
    category: str = Form(...),
    points: int = Form(...),
    flag: str = Form(...),
    external_url: str = Form(None),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if challenge:
        challenge.title = title
        challenge.description = description
        challenge.long_description = long_description or description
        challenge.hint = hint
        challenge.category = category
        challenge.points = points
        challenge.flag = flag
        challenge.external_url = external_url
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.get("/scoreboard")
def show_scoreboard(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.score.desc()).all()
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
    
    return templates.TemplateResponse(
        request,
        "zerofour/challenge.html",
        {
            "request": request,
            "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
            "challenge": challenge,
            "user_points": user_points,
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

@app.post("/challenge/{challenge_id}/check")
def check_flag(
    request: Request,
    challenge_id: int,
    flag: str = Form(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    challenge = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje!")
    
    logged_in_user = current_user.username if current_user else None
    user_points = get_user_points(db, current_user)
    
    if not logged_in_user:
        return templates.TemplateResponse(
            request,
            "zerofour/challenge.html",
            {
                "request": request,
                "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
                "challenge": challenge,
                "message": "Musisz byc zalogowany, aby zdobyc punkty!",
                "solved": False,
                "user_points": user_points,
                "active_page": "home"
            }
        )
    
    user = current_user
    if not user:
        return templates.TemplateResponse(
            request,
            "zerofour/challenge.html",
            {
                "request": request,
                "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
                "challenge": challenge,
                "message": "Nie znaleziono uzytkownika!",
                "solved": False,
                "user_points": user_points,
                "active_page": "home"
            }
        )
    
    existing_solve = db.query(models.Solve).filter(
        models.Solve.user_id == user.id,
        models.Solve.challenge_id == challenge.id
    ).first()
    
    if existing_solve:
        return templates.TemplateResponse(
            request,
            "zerofour/challenge.html",
            {
                "request": request,
                "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
                "challenge": challenge,
                "message": "Juz rozwiazales to zadanie!",
                "solved": True,
                "user_points": user_points,
                "active_page": "home"
            }
        )
    
    if flag.strip() == challenge.flag:
        user.score += challenge.points
        new_solve = models.Solve(
            user_id=user.id,
            challenge_id=challenge.id
        )
        db.add(new_solve)
        db.commit()
        
        user_points = user.score
        
        return templates.TemplateResponse(
            request,
            "zerofour/challenge.html",
            {
                "request": request,
                "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
                "challenge": challenge,
                "message": f"Poprawna flaga! +{challenge.points} punktow!",
                "solved": True,
                "user_points": user_points,
                "active_page": "home"
            }
        )
    else:
        return templates.TemplateResponse(
            request,
            "zerofour/challenge.html",
            {
                "request": request,
                "username": logged_in_user,
            "is_admin": bool(current_user and current_user.role == "admin"),
                "challenge": challenge,
                "message": "Niepoprawna flaga! Sprobuj ponownie.",
                "solved": False,
                "user_points": user_points,
                "active_page": "home"
            }
        )