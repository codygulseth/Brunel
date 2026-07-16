from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


DATABASE_PATH = Path(__file__).resolve().parents[2] / "ai_project_engineer.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


def make_engine(url: str = DATABASE_URL):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_tables() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

