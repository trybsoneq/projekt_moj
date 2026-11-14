"""Database configuration shared by migrations and the web application."""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BASE_DIR / "ctf_platform.db"
DATABASE_PATH = Path(
    os.getenv("CTF_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
).expanduser().resolve()

# An absolute SQLite path ensures CLI migrations and Uvicorn use the same file,
# even when the process is started from a different working directory.
SQLALCHEMY_DATABASE_URL = URL.create(
    "sqlite",
    database=str(DATABASE_PATH),
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(connection, _record):
    """Enforce foreign keys and avoid immediate 'database is locked' failures."""
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
