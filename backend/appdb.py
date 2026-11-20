"""Application database (accounts, bots, chats, broadcasts, transfers …) — SQLite.

Every query in the web layer is scoped to the signed-in account; this module only
owns the schema, migrations and small helpers.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import secrets
import sqlite3
import threading
from typing import Any, Iterable, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("APP_DB_PATH") or os.path.normpath(os.path.join(BASE_DIR, "..", "storage", "app.db"))

_local = threading.local()


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def now_iso() -> str:
    return utcnow().isoformat(timespec="milliseconds") + "Z"


def iso_in(**delta) -> str:
    return (utcnow() + datetime.timedelta(**delta)).isoformat(timespec="milliseconds") + "Z"


def parse_iso(v: Optional[str]) -> Optional[datetime.datetime]:
    if not v:
        return None
    try:
        return datetime.datetime.fromisoformat(v.replace("Z", "").split("+")[0])
    except Exception:
        return None


def new_id(prefix: str, nbytes: int = 8) -> str:
    return f"{prefix}{secrets.token_hex(nbytes)}"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextlib.contextmanager
def db():
    """One short transaction. Commits on success, rolls back on error."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


@contextlib.contextmanager
def read():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def rows(conn, q: str, args: Iterable = ()) -> list:
    return conn.execute(q, tuple(args)).fetchall()


def one(conn, q: str, args: Iterable = ()):
    return conn.execute(q, tuple(args)).fetchone()


def jload(v: Any, default):
    if v is None or v == "":
        return default
    try:
        if isinstance(v, str) and v.startswith("enc:"):
            from backend import security
            v = security.decrypt(v)
        return json.loads(v)
    except Exception:
        return default


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        name TEXT NOT NULL, plan TEXT DEFAULT 'Matrix Free', avatar TEXT, is_email_verified INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id TEXT NOT NULL, email TEXT NOT NULL, client_metadata TEXT,
        ip TEXT, user_agent TEXT, remember_me INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
        created_at TEXT, expires_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS email_otps (
        id TEXT PRIMARY KEY, email TEXT NOT NULL, code TEXT NOT NULL, expires_at TEXT NOT NULL,
        is_used INTEGER DEFAULT 0, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS bots (
        id TEXT PRIMARY KEY, user_id TEXT, bot_numeric_id TEXT, username TEXT NOT NULL, name TEXT NOT NULL,
        status TEXT DEFAULT 'stopped', active_users INTEGER DEFAULT 0, total_commands INTEGER DEFAULT 0,
        category TEXT DEFAULT 'Operations', last_active TEXT, uptime TEXT DEFAULT '', version TEXT DEFAULT 'v1.0.0',
        folder TEXT DEFAULT '', is_pinned INTEGER DEFAULT 0, photo_url TEXT, webhook_url TEXT, token TEXT,
        faster_response INTEGER DEFAULT 1, auto_translate INTEGER DEFAULT 0, mini_app_title TEXT, mini_app_url TEXT,
        description TEXT, commands_json TEXT, env_vars_json TEXT, errors_json TEXT, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS folders (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT,
        UNIQUE(user_id, name))""",
    """CREATE TABLE IF NOT EXISTS global_admins (
        user_id TEXT NOT NULL, telegram_id TEXT NOT NULL, added_at TEXT, PRIMARY KEY (user_id, telegram_id))""",
    """CREATE TABLE IF NOT EXISTS store_bots (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL, description TEXT, rating REAL DEFAULT 0,
        forks INTEGER DEFAULT 0, category TEXT, tags_json TEXT, commands_count INTEGER DEFAULT 0, author_name TEXT,
        version TEXT, avatar_url TEXT, commands_json TEXT, owner_id TEXT)""",
    """CREATE TABLE IF NOT EXISTS broadcasts (
        id TEXT PRIMARY KEY, user_id TEXT, title TEXT NOT NULL, target_bot_ids TEXT, target_bot_usernames TEXT,
        message_type TEXT DEFAULT 'Text', message_text TEXT NOT NULL, parse_mode TEXT DEFAULT 'HTML',
        inline_buttons TEXT, language_filter TEXT, status TEXT DEFAULT 'Active', target_user_limit INTEGER,
        total_target_users INTEGER DEFAULT 0, sent_count INTEGER DEFAULT 0, in_progress_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0, cleaned_failed INTEGER DEFAULT 0, delivery_speed TEXT DEFAULT '30 msgs/sec',
        bot_stats_json TEXT, failed_recipients_json TEXT, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, telegram_id TEXT NOT NULL, name TEXT, username TEXT,
        avatar_color TEXT, photo_url TEXT, last_active TEXT, last_message TEXT, is_blocked INTEGER DEFAULT 0,
        messages_count INTEGER DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY, user_id TEXT, title TEXT NOT NULL, message TEXT NOT NULL, time TEXT,
        is_read INTEGER DEFAULT 0, type TEXT DEFAULT 'info', created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS settings (user_id TEXT PRIMARY KEY, settings_json TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS recycle_bin (
        id TEXT PRIMARY KEY, item_type TEXT NOT NULL, data_json TEXT NOT NULL, deleted_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY, value TEXT)""",
    """CREATE TABLE IF NOT EXISTS support_tickets (
        id TEXT PRIMARY KEY, name TEXT, email TEXT, message TEXT, category TEXT, created_at TEXT,
        user_id TEXT, status TEXT DEFAULT 'open', subject TEXT, department TEXT, priority TEXT DEFAULT 'Normal',
        updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS support_ticket_replies (
        id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, user_id TEXT, is_staff INTEGER DEFAULT 0,
        message TEXT NOT NULL, created_at TEXT, author_name TEXT)""",
    """CREATE TABLE IF NOT EXISTS transfers (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, bot_name TEXT, bot_username TEXT, bot_numeric_id TEXT,
        from_user_id TEXT NOT NULL, to_user_id TEXT NOT NULL, from_email TEXT, to_email TEXT,
        status TEXT DEFAULT 'pending', verification_token TEXT, created_at TEXT, expires_at TEXT, responded_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS broadcast_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bc_id TEXT NOT NULL, bot_id TEXT NOT NULL, telegram_id TEXT NOT NULL,
        kind TEXT NOT NULL, reason TEXT, failed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS broadcast_done (
        bc_id TEXT NOT NULL, bot_id TEXT NOT NULL, telegram_id TEXT NOT NULL, PRIMARY KEY (bc_id, bot_id, telegram_id)) WITHOUT ROWID""",
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT, bot_id TEXT, kind TEXT, tg_user TEXT, ts TEXT)""",
    """CREATE TABLE IF NOT EXISTS connect_links (
        code_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS bot_kv (
        bot_id TEXT NOT NULL, record_key TEXT NOT NULL, record_value TEXT, value_type TEXT DEFAULT 'string',
        updated_at TEXT, PRIMARY KEY (bot_id, record_key))""",
]

COLUMNS = [
    ("users", "suspended INTEGER DEFAULT 0"),
    ("users", "suspended_reason TEXT"),
    ("broadcasts", "reasons_json TEXT"),
    ("broadcasts", "unreachable_count INTEGER DEFAULT 0"),
    ("broadcasts", "cleaned_count INTEGER DEFAULT 0"),
    ("broadcasts", "pin_message INTEGER DEFAULT 0"),
    ("events", "ms INTEGER"),
    ("events", "cmd TEXT"),
    ("bots", "origin TEXT"),
    ("broadcasts", "media_source TEXT"),
    ("broadcasts", "media_ref TEXT"),
    ("broadcasts", "media_name TEXT"),
    ("transfers", "options_json TEXT"),
    ("users", "points INTEGER"),
    ("users", "extra_points INTEGER DEFAULT 0"),
    ("users", "plan_expires_at TEXT"),
    ("users", "last_free_reset TEXT"),
    ("users", "cost_carry REAL DEFAULT 0"),
    ("notifications", "link TEXT"),
    ("users", "telegram_chat_id TEXT"),
    ("users", "telegram_first_name TEXT"),
    ("users", "telegram_username TEXT"),
    ("users", "telegram_connected INTEGER DEFAULT 0"),
    ("users", "telegram_connected_at TEXT"),
    ("users", "telegram_alerts_json TEXT"),
    ("sessions", "token_hash TEXT"),
    ("recycle_bin", "user_id TEXT"),
    ("support_tickets", "user_id TEXT"),
    ("support_tickets", "status TEXT DEFAULT 'open'"),
    ("support_tickets", "subject TEXT"),
    ("support_tickets", "department TEXT"),
    ("support_tickets", "priority TEXT DEFAULT 'Normal'"),
    ("support_tickets", "updated_at TEXT"),
    ("support_ticket_replies", "seen_at TEXT"),
    ("support_ticket_replies", "delivered_at TEXT"),
    ("chats", "bot_blocked INTEGER DEFAULT 0"),
    ("chats", "first_seen TEXT"),
    ("chats", "language_code TEXT"),
    ("bots", "photo_checked_at TEXT"),
    ("broadcasts", "blocked_count INTEGER DEFAULT 0"),
    ("broadcasts", "started_at TEXT"),
    ("broadcasts", "finished_at TEXT"),
    ("broadcasts", "paused_seconds REAL DEFAULT 0"),
    ("store_bots", "owner_id TEXT"),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bcf_bc ON broadcast_failures(bc_id, kind, bot_id)",
    "CREATE INDEX IF NOT EXISTS idx_bcf_tg ON broadcast_failures(bc_id, bot_id, telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_bots_user ON bots(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_chats_bot ON chats(bot_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_chats_bot_tg ON chats(bot_id, telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_hash ON sessions(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_bc_user ON broadcasts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers(from_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_transfers_to ON transfers(to_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_owner_ts ON events(owner_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_users_tgchat ON users(telegram_chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ticket_replies_tid ON support_ticket_replies(ticket_id)",
]

DEFAULT_ALERTS = {
    "botStartStop": True, "botTransfers": True, "criticalCrashes": True, "broadcastReports": True,
    "newSubscribers": False, "securityAlerts": True, "dailyDigest": False,
    "botErrors": True, "lowPoints": True, "broadcastStarted": False,
}

DEFAULT_POINTS = int(os.environ.get("DEFAULT_POINTS", "1000"))


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = connect()
    try:
        for q in SCHEMA:
            conn.execute(q)
        for table, coldef in COLUMNS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if coldef.split()[0] not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
        done = conn.execute("SELECT value FROM platform_settings WHERE key='schema_v2'").fetchone()
        if not done:
            conn.execute("DELETE FROM sessions")
            conn.execute("UPDATE users SET telegram_connected=0, telegram_chat_id=NULL, telegram_username=NULL, telegram_connected_at=NULL")
            conn.execute("DELETE FROM global_admins")
            conn.execute("DELETE FROM recycle_bin WHERE user_id IS NULL")
            conn.execute("DELETE FROM store_bots WHERE owner_id IS NULL")
            conn.execute("DELETE FROM email_otps")
            conn.execute("UPDATE bots SET status='stopped' WHERE status NOT IN ('working','stopped')")
            conn.execute("UPDATE broadcasts SET status='Failed' WHERE status IN ('Active','In Progress')")
            conn.execute("UPDATE users SET plan='Free' WHERE plan IN ('VIP Enterprise Cluster','Creator Pro Node')")
            conn.execute("UPDATE users SET points=? WHERE points IS NULL", (DEFAULT_POINTS,))
            try:
                for r in conn.execute("SELECT DISTINCT user_id, folder FROM bots WHERE folder IS NOT NULL AND folder != '' AND user_id IS NOT NULL").fetchall():
                    conn.execute("INSERT OR IGNORE INTO folders (id,user_id,name,created_at) VALUES (?,?,?,?)",
                                 (new_id("fld_", 4), r["user_id"], r["folder"], now_iso()))
            except Exception:
                pass
            conn.execute("INSERT OR REPLACE INTO platform_settings (key,value) VALUES ('schema_v2','1')")
        for q in INDEXES:
            try:
                conn.execute(q)
            except Exception:
                pass
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bots_token ON bots(token) WHERE token IS NOT NULL AND token != ''")
        except Exception:
            pass
        conn.execute("DELETE FROM events WHERE ts < ?", (iso_in(hours=-72),))
    finally:
        conn.close()


def _link_cat(link: str) -> str:
    l = (link or "").lower()
    return ("transfers" if "transfers" in l else "broadcasts" if "broadcast" in l else "billing" if "plans" in l
            else "bots" if l.startswith("bot:") else "account")


def notify(user_id: str, title: str, message: str, kind: str = "info", link: str = "") -> None:
    try:
        with db() as c:
            r = one(c, "SELECT settings_json FROM settings WHERE user_id=?", (user_id,))
            st = jload(r["settings_json"], {}) if r else {}
            if st.get("notificationsEnabled") is False:
                return
            prefs = st.get("notificationTypes") or {}
            if isinstance(prefs, dict) and prefs.get(_link_cat(link)) is False:
                return
            c.execute(
                "INSERT INTO notifications (id,user_id,title,message,time,is_read,type,created_at,link) VALUES (?,?,?,?,?,0,?,?,?)",
                (new_id("n_", 6), user_id, title[:200], message[:2000], "Just now", kind, now_iso(), (link or "")[:120]),
            )
    except Exception:
        pass


def log_event(owner_id: str, bot_id: str, kind: str, tg_user: Any = None, ms: Any = None, cmd: Any = None) -> None:
    try:
        with db() as c:
            c.execute("INSERT INTO events (owner_id,bot_id,kind,tg_user,ts,ms,cmd) VALUES (?,?,?,?,?,?,?)",
                      (owner_id, bot_id, kind, str(tg_user) if tg_user is not None else None, now_iso(), int(ms) if ms is not None else None,
                       str(cmd)[:100] if cmd else None))
    except Exception:
        pass


def get_points(user_id: str) -> int:
    with read() as c:
        r = one(c, "SELECT points FROM users WHERE id=?", (user_id,))
    return int(r["points"] or 0) if r else 0


def split_points(user_id: str) -> dict:
    with read() as c:
        r = one(c, "SELECT points, extra_points FROM users WHERE id=?", (user_id,))
    total = int((r["points"] if r else 0) or 0)
    extra = max(0, min(total, int((r["extra_points"] if r else 0) or 0)))
    return {"total": total, "plan": total - extra, "extra": extra}


def _rate(name: str, default: float) -> float:
    try:
        return max(0.01, float(os.environ.get(name) or default))
    except ValueError:
        return default


def charge_points(user_id: str, amount: int = 1) -> Optional[int]:
    with db() as c:
        r = one(c, "SELECT points, extra_points, cost_carry FROM users WHERE id=?", (user_id,))
        if not r:
            return None
        total = int(r["points"] or 0)
        extra = max(0, min(total, int(r["extra_points"] or 0)))
        plan = total - extra
        carry = float(r["cost_carry"] or 0.0)
        rate = _rate("PLAN_POINT_RATE", 1.0) if plan > 0 else _rate("EXTRA_POINT_RATE", 1.5)
        carry += rate * max(0, int(amount))
        whole = int(carry + 1e-9)
        if whole > total:
            return None
        carry = max(0.0, carry - whole)
        from_plan = min(plan, whole)
        from_extra = whole - from_plan
        c.execute("UPDATE users SET points=?, extra_points=?, cost_carry=? WHERE id=?",
                  (total - whole, extra - from_extra, carry, user_id))
        return total - whole
