import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    import logging
    from dotenv import dotenv_values
    path = BASE_DIR / ".env"
    if not path.exists():
        logging.getLogger("config").warning(
            ".env not found at %s - create it or use Admin > Settings.", path)
        return
    load_dotenv(path, override=False)
    for k, v in dotenv_values(path).items():
        if v is not None and not os.environ.get(k):
            os.environ[k] = v


_load_env()
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(STORAGE_DIR / "captcha").mkdir(parents=True, exist_ok=True)


def _default_sqlite_url() -> str:
    db_path = (STORAGE_DIR / "platform.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


def _normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return _default_sqlite_url()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if not url.startswith("sqlite"):
        return url
    raw = url.replace("sqlite:///", "", 1).replace("\\", "/")
    if raw.startswith("./") or (not raw.startswith("/") and not (len(raw) > 1 and raw[1] == ":")):
        abs_path = (BASE_DIR / raw.lstrip("./").rstrip("/")).resolve().as_posix()
        return f"sqlite:///{abs_path}"
    try:
        Path(raw).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return f"sqlite:///{raw}"


def ensure_secret_key() -> str:
    import logging
    import secrets as _secrets
    key = (os.getenv("SECRET_KEY") or "").strip()
    is_prod = (os.getenv("NODE_ENV") or "").lower() == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT"))
    if key and len(key) >= 16:
        return key
    if is_prod:
        logging.getLogger("config").error(
            "SECRET_KEY is missing or too short. Set SECRET_KEY in Railway Variables "
            "(openssl rand -hex 32)."
        )
        key = _secrets.token_hex(32)
        os.environ["SECRET_KEY"] = key
        logging.getLogger("config").warning("Using ephemeral SECRET_KEY for this process only.")
        return key
    if not key:
        key = _secrets.token_hex(24)
        os.environ["SECRET_KEY"] = key
        logging.getLogger("config").warning("Generated ephemeral SECRET_KEY for local dev.")
    return key


SECRET_KEY = ensure_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", _default_sqlite_url()))
STORAGE_DIR = str(STORAGE_DIR)

REDIS_URL = (os.getenv("REDIS_URL") or os.getenv("BM_REDIS_URL") or "").strip()

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
DEFAULT_POINTS = int(os.getenv("DEFAULT_POINTS", "100000"))
POINTS_PER_COMMAND = int(os.getenv("POINTS_PER_COMMAND", "1"))
MAX_EXEC_SECONDS = int(os.getenv("MAX_EXEC_SECONDS", "160"))
TELEGRAM_API_ROOT = os.getenv("TELEGRAM_API_ROOT", "https://api.telegram.org").rstrip("/")
