import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./industrial_furnace_v1.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {"connect_args": connect_args}
if DATABASE_URL == "sqlite:///:memory:":
    engine_kwargs["poolclass"] = StaticPool
elif not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True})
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(projects)").fetchall()}
            if "department" not in columns:
                connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN department VARCHAR(64) NOT NULL DEFAULT '工业炉'")
