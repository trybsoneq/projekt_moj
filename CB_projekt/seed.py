from database import SessionLocal
import models


def seed_database():
    db = SessionLocal()
    try:
        # Konto administratora tworzymy wyłącznie przez create_admin.py.
        # Seed nie może przywracać znanego hasła admin/admin.
        if db.query(models.Challenge).count() == 0:
            tasks = [
                models.Challenge(
                    title="Tajemniczy plik",
                    description="Znajdź flagę ukrytą w tym pliku tekstowym.",
                    category="Forensics",
                    points=50,
                    flag="CTF{ukryty_tekst}",
                ),
                models.Challenge(
                    title="Szyfr Cezara",
                    description="Rozszyfruj tę dziwną wiadomość: WUDLQ JR.",
                    category="Cryptography",
                    points=100,
                    flag="CTF{TRAIN_GO}",
                ),
                models.Challenge(
                    title="Dziurawa strona",
                    description="Zaloguj się jako admin na tej stronie omijając hasło.",
                    category="Web Exploitation",
                    points=200,
                    flag="CTF{sql_injection_master}",
                ),
            ]
            db.add_all(tasks)
            print("Dodano 3 testowe zadania do bazy!")
        else:
            print("Zadania już istnieją w bazie, pomijam.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    print("Rozpoczynam dodawanie danych...")
    seed_database()
    print("Zakończono!")
