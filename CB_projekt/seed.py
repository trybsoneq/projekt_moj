from database import SessionLocal, engine, Base
import models
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_database():
    db = SessionLocal()
    
    # 1. Tworzymy konto admina
    admin_user = db.query(models.User).filter(models.User.username == "admin").first()
    if not admin_user:
        admin = models.User(
            username="admin",
            password_hash=pwd_context.hash("admin")
        )
        db.add(admin)
        print("✅ Utworzono konto admina (login: admin, hasło: admin)")

    # 2. Tworzymy 3 testowe zadania, jeśli baza jest pusta
    if db.query(models.Challenge).count() == 0:
        tasks = [
            models.Challenge(title="Tajemniczy plik", description="Znajdź flagę ukrytą w tym pliku tekstowym.", category="Forensics", points=50, flag="CTF{ukryty_tekst}"),
            models.Challenge(title="Szyfr Cezara", description="Rozszyfruj tę dziwną wiadomość: WUDLQ JR.", category="Cryptography", points=100, flag="CTF{TRAIN_GO}"),
            models.Challenge(title="Dziurawa strona", description="Zaloguj się jako admin na tej stronie omijając hasło.", category="Web Exploitation", points=200, flag="CTF{sql_injection_master}")
        ]
        db.add_all(tasks)
        print("✅ Dodano 3 testowe zadania do bazy!")
    else:
        print("⚠️ Zadania już istnieją w bazie, pomijam.")

    db.commit()
    db.close()

if __name__ == "__main__":
    print("Rozpoczynam dodawanie danych...")
    seed_database()
    print("Zakończono!")