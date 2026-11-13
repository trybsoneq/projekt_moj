# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Nazwa pliku naszej bazy danych SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./ctf_platform.db"

# Engine to serce połączenia z bazą. 
# check_same_thread=False jest potrzebne tylko dla SQLite w FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Sesja pozwala nam wykonywać operacje na bazie (dodawanie, usuwanie itp.)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Z tej klasy będą dziedziczyć nasze modele/tabele
Base = declarative_base()

# Funkcja pomocnicza, którą wykorzystamy później w API do bezpiecznego otwierania/zamykania sesji
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()