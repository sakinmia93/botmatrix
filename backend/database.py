"""Database engine — SQLite (dev) or PostgreSQL (production).

Set DATABASE_URL in Railway Variables:
  postgresql://postgres:****@postgres.railway.internal:5432/railway
(normalized to postgresql+psycopg2:// automatically via config.py)
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import DATABASE_URL
from pathlib import Path
import logging

log = logging.getLogger("database")

if DATABASE_URL.startswith("sqlite"):
    _raw = DATABASE_URL.replace("sqlite:///", "", 1).replace("\\", "/")
    try:
        Path(_raw).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_postgres = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")

connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if _is_sqlite:
    connect_args = {"check_same_thread": False, "timeout": 30}
    engine_kwargs.update(pool_size=5, max_overflow=10)
elif _is_postgres:
    import os
    engine_kwargs.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    )
    safe = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "(local)"
    log.info("SQLAlchemy engine: postgres host/db = %s", safe)

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> dict:
    from sqlalchemy import text
    try:
        t0 = __import__("time").time()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ms = round((__import__("time").time() - t0) * 1000, 1)
        return {"ok": True, "backend": "postgres" if _is_postgres else "sqlite", "ping_ms": ms}
    except Exception as e:
        return {"ok": False, "backend": "postgres" if _is_postgres else "sqlite", "error": type(e).__name__}


def run_compat_migrations():
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "bots" in tables:
        cols = {c["name"] for c in insp.get_columns("bots")}
        with engine.begin() as conn:
            if "public_id" not in cols:
                conn.execute(text("ALTER TABLE bots ADD COLUMN public_id VARCHAR(32)"))
            if "storage_limit_mb" not in cols:
                conn.execute(text("ALTER TABLE bots ADD COLUMN storage_limit_mb INTEGER DEFAULT 100"))
            if "auto_translate" not in cols:
                conn.execute(text("ALTER TABLE bots ADD COLUMN auto_translate BOOLEAN DEFAULT 0"))
            if "faster_response" not in cols:
                conn.execute(text("ALTER TABLE bots ADD COLUMN faster_response BOOLEAN DEFAULT 1"))
