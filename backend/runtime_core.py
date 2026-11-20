"""Bot runtime core: Telegram long-polling + command pipeline on the v15 engine."""
from __future__ import annotations
import logging, threading, time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Set
from backend import appdb, security, tg
from backend.database import SessionLocal, Base, engine as engine_db
from backend import models as em
from backend.sandbox.runner import run_command, match_command, extract_message, _chain_begin, update_type_of

log = logging.getLogger("runtime")
POINTS_PER_COMMAND = 1
_pool = ThreadPoolExecutor(max_workers=64, thread_name_prefix="upd")
_user_locks: Dict[tuple, threading.Lock] = {}
_ul = threading.Lock()
_workers: Dict[str, "Worker"] = {}
_lock = threading.Lock()
_stopping: Set[str] = set()
_offsets: Dict[str, int] = {}
ALL_UPDATE_TYPES = (
    "message", "edited_message", "channel_post", "edited_channel_post",
    "callback_query", "inline_query", "chosen_inline_result",
    "shipping_query", "pre_checkout_query", "poll", "poll_answer",
    "my_chat_member", "chat_member", "chat_join_request",
)

def init_engine() -> None:
    try:
        Base.metadata.create_all(bind=engine_db)
        try:
            from backend.database import run_compat_migrations
            run_compat_migrations()
        except Exception:
            log.exception("compat migrations")
    except Exception:
        log.exception("engine init")

def _env_code(env_vars: list) -> str:
    lines = []
    for e in env_vars or []:
        if not isinstance(e, dict):
            continue
        k = str(e.get("key") or e.get("name") or "").strip()
        if not k:
            continue
        v = e.get("value")
        if v is None:
            v = ""
        lines.append(f"{k}={v}")
    return "\n".join(lines)

def sync_bot(bot_id: str, db=None) -> Optional[int]:
    with appdb.read() as c:
        b = appdb.one(c, "SELECT * FROM bots WHERE id=?", (bot_id,))
        if not b:
            return None
        u = appdb.one(c, "SELECT id, points FROM users WHERE id=?", (b["user_id"],))
    if not u:
        return None
    token = security.decrypt(b["token"] or "")
    own = db is None
    db = db or SessionLocal()
    try:
        acc_email = f"{u['id']}@matrix.local"
        acc = db.query(em.Account).filter_by(email=acc_email).first()
        if not acc:
            acc = em.Account(email=acc_email, hashed_password="!", points=int(u["points"] or 0))
            db.add(acc)
            db.flush()
        acc.points = int(u["points"] or 0)
        eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
        if not eb and token:
            eb = db.query(em.Bot).filter_by(token=token).first()
            if eb:
                eb.public_id = bot_id
        if not eb:
            eb = em.Bot(public_id=bot_id, owner_id=acc.id, name=b["name"], token=token or f"none:{bot_id}")
            db.add(eb)
            try:
                db.flush()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                eb = db.query(em.Bot).filter_by(token=token).first() if token else None
                if not eb:
                    eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
                if not eb:
                    raise
                eb.public_id = bot_id
        eb.owner_id = acc.id
        eb.name = b["name"]
        eb.username = (b["username"] or "").lstrip("@")
        if token:
            eb.token = token
        eb.auto_translate = bool(b["auto_translate"])
        eb.faster_response = bool(b["faster_response"])
        eb.is_running = b["status"] == "working"
        eb.deleted_at = None
        cmds = appdb.jload(b["commands_json"], [])
        want = {}
        for cmd in cmds:
            name = str(cmd.get("name") or "").strip()
            if not name:
                continue
            want[name] = cmd
            if name not in ("@", "~", "!", "*", ".env") and not name.startswith("/handler_"):
                alt = name[1:] if name.startswith("/") else ("/" + name)
                if alt and alt not in want:
                    want[alt] = cmd
            for al in cmd.get("aliases") or []:
                al = str(al).strip()
                if al and al not in want:
                    want[al] = cmd
        env = _env_code(appdb.jload(b["env_vars_json"], []))
        if env:
            want[".env"] = {"code": env}
        have = {c.trigger: c for c in db.query(em.Command).filter_by(bot_id=eb.id).all()}
        for name, c in list(have.items()):
            if name not in want:
                db.delete(c)
        for name, cmd in want.items():
            row = have.get(name)
            code = str(cmd.get("code") or "")
            if row:
                row.code = code
            else:
                db.add(em.Command(bot_id=eb.id, trigger=name, code=code))
        db.commit()
        return int(eb.id)
    except Exception:
        log.exception("sync_bot")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        if own:
            try:
                db.close()
            except Exception:
                pass

def track_chat(bot_id: str, owner_id: str, update: dict) -> Optional[dict]:
    try:
        msg = extract_message(update) or {}
        frm = msg.get("from") or update.get("callback_query", {}).get("from") or {}
        tid = frm.get("id")
        if not tid:
            return None
        name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) or frm.get("username") or str(tid)
        username = frm.get("username") or ""
        blocked = False
        with appdb.db() as c:
            row = appdb.one(c, "SELECT id,is_blocked FROM chats WHERE bot_id=? AND telegram_id=?", (bot_id, str(tid)))
            if row:
                c.execute(
                    "UPDATE chats SET name=?, username=?, last_active=?, first_seen=COALESCE(NULLIF(first_seen,''), ?), messages_count=COALESCE(messages_count,0)+1 WHERE id=?",
                    (name, username, appdb.now_iso(), appdb.now_iso(), row["id"]),
                )
                blocked = bool(row["is_blocked"])
            else:
                try:
                    now = appdb.now_iso()
                    c.execute(
                        "INSERT INTO chats (id,bot_id,telegram_id,name,username,last_active,first_seen,messages_count,is_blocked,bot_blocked) VALUES (?,?,?,?,?,?,?,1,0,0)",
                        (appdb.new_id("ch_", 8), bot_id, str(tid), name, username, now, now),
                    )
                except Exception:
                    pass
        return {"telegram_id": tid, "name": name, "blocked": blocked}
    except Exception:
        log.exception("track_chat")
        return None

def _user_lock(bot_pk: int, uid) -> threading.Lock:
    key = (bot_pk, uid or 0)
    with _ul:
        if key not in _user_locks:
            _user_locks[key] = threading.Lock()
        return _user_locks[key]

def update_types_wanted() -> list:
    return list(ALL_UPDATE_TYPES)

def process_update(bot_id: str, update: dict) -> None:
    try:
        with appdb.read() as c:
            b = appdb.one(c, "SELECT id,user_id,status FROM bots WHERE id=?", (bot_id,))
        if not b or b["status"] != "working":
            return
        owner = b["user_id"]
        info = track_chat(bot_id, owner, update)
        db = SessionLocal()
        try:
            eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
            if not eb:
                sync_bot(bot_id)
                eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
            if not eb:
                return
            if not eb.is_running:
                eb.is_running = True
                db.commit()
            acc = db.query(em.Account).filter_by(id=eb.owner_id).first()
            if not acc:
                return
            _run_pipeline(db, eb, bot_id, owner, update)
        finally:
            db.close()
    except Exception:
        log.exception("process_update")

def _run_pipeline(db, eb, bot_id: str, owner: str, update: dict) -> None:
    try:
        cmds = db.query(em.Command).filter_by(bot_id=eb.id).all()
        commands = [{"trigger": c.trigger, "code": c.code, "name": c.trigger} for c in cmds]
        secrets = {}
        acc = db.query(em.Account).filter_by(id=eb.owner_id).first()
        msg = extract_message(update) or {}
        text = (msg.get("text") or msg.get("caption") or "") or ""
        matched = match_command(commands, text, update)
        if matched:
            run_command(db, eb, acc, matched, update, secrets=secrets)
    except Exception:
        log.exception("_run_pipeline")

def run_external(eb_pk: int, trigger: str, update: dict, options=None) -> dict:
    db = SessionLocal()
    try:
        eb = db.query(em.Bot).filter_by(id=int(eb_pk)).first()
        if not eb:
            return {"ok": False, "error": "bot not found"}
        bot_id = eb.public_id or str(eb.id)
        sync_bot(bot_id, db)
        eb = db.query(em.Bot).filter_by(id=int(eb_pk)).first()
        acc = db.query(em.Account).filter_by(id=eb.owner_id).first() if eb else None
        if not eb or not acc:
            return {"ok": False, "error": "bot/account missing"}
        cmds = db.query(em.Command).filter_by(bot_id=eb.id).all()
        cmd = next((c for c in cmds if c.trigger == trigger or c.trigger == f"/{trigger.lstrip('/')}"), None)
        if not cmd:
            cmd = {"trigger": trigger, "code": "", "name": trigger}
        else:
            cmd = {"trigger": cmd.trigger, "code": cmd.code, "name": cmd.trigger}
        r = run_command(db, eb, acc, cmd, update, secrets={}, options=options or {})
        return {"ok": True, "webhook_result": r.get("webhook_result") if isinstance(r, dict) else None, **(r if isinstance(r, dict) else {})}
    except Exception as e:
        log.exception("run_external")
        return {"ok": False, "error": str(e), "webhook_result": None}
    finally:
        db.close()

def stop_all_for_user(user_id: str, reason: str = "") -> int:
    n = 0
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT id FROM bots WHERE user_id=? AND status='working'", (user_id,))
    for r in rows:
        try:
            set_running(r["id"], False)
            n += 1
        except Exception:
            pass
    return n

def _auto_stop(bot_id: str, reason: str) -> None:
    try:
        set_running(bot_id, False)
        log.warning("auto-stop %s: %s", bot_id, reason)
    except Exception:
        log.exception("auto-stop")

class Worker(threading.Thread):
    def __init__(self, bot_id: str, token: str, fast: bool):
        super().__init__(daemon=True, name=f"poll-{bot_id[:8]}")
        self.bot_id = bot_id
        self.token = token
        self.fast = fast
        self._stop = threading.Event()

    def run(self):
        offset = _offsets.get(self.bot_id, 0)
        while not self._stop.is_set() and self.bot_id not in _stopping:
            try:
                ups = tg.get_updates(self.token, offset=offset, timeout=25 if not self.fast else 5)
                for up in ups or []:
                    offset = max(offset, int(up.get("update_id", 0)) + 1)
                    _offsets[self.bot_id] = offset
                    _pool.submit(process_update, self.bot_id, up)
            except Exception as e:
                if "401" in str(e) or "Unauthorized" in str(e):
                    _auto_stop(self.bot_id, str(e))
                    break
                log.exception("poll %s", self.bot_id)
                time.sleep(3)
        with _lock:
            _workers.pop(self.bot_id, None)

def is_running(bot_id: str) -> bool:
    with _lock:
        return bot_id in _workers and bot_id not in _stopping

def stop_worker(bot_id: str) -> None:
    with _lock:
        _stopping.add(bot_id)
        w = _workers.get(bot_id)
    if w:
        w._stop.set()
        try:
            w.join(timeout=2)
        except Exception:
            pass
    with _lock:
        _workers.pop(bot_id, None)
        _stopping.discard(bot_id)

def set_running(bot_id: str, running: bool, db=None) -> dict:
    if not running:
        stop_worker(bot_id)
        with appdb.db() as c:
            c.execute("UPDATE bots SET status='stopped', uptime='', updated_at=? WHERE id=?", (appdb.now_iso(), bot_id))
        try:
            s = SessionLocal()
            try:
                eb = s.query(em.Bot).filter_by(public_id=bot_id).first()
                if eb:
                    eb.is_running = False
                    s.commit()
            finally:
                s.close()
        except Exception:
            pass
        return {"running": False}
    with _lock:
        if bot_id in _workers:
            with appdb.db() as c:
                c.execute(
                    "UPDATE bots SET status='working', uptime=COALESCE(NULLIF(uptime,''), ?), updated_at=? WHERE id=?",
                    (appdb.now_iso(), appdb.now_iso(), bot_id),
                )
            return {"running": True}
    with appdb.read() as c:
        b = appdb.one(c, "SELECT token, faster_response FROM bots WHERE id=?", (bot_id,))
    if not b:
        raise ValueError("Bot not found")
    token = security.decrypt(b["token"] or "")
    if not token:
        raise ValueError("This bot has no token yet.")
    with appdb.db() as c:
        c.execute(
            "UPDATE bots SET status='working', uptime=COALESCE(NULLIF(uptime,''), ?), updated_at=? WHERE id=?",
            (appdb.now_iso(), appdb.now_iso(), bot_id),
        )
    pk = sync_bot(bot_id)
    if not pk:
        with appdb.db() as c:
            c.execute("UPDATE bots SET status='stopped', updated_at=? WHERE id=?", (appdb.now_iso(), bot_id))
        raise ValueError("Could not sync bot into the runtime engine. Check the bot token.")
    try:
        s = SessionLocal()
        try:
            eb = s.query(em.Bot).filter_by(public_id=bot_id).first()
            if eb:
                eb.is_running = True
                s.commit()
        finally:
            s.close()
    except Exception:
        log.exception("force is_running")
    w = Worker(bot_id, token, bool(b["faster_response"]))
    with _lock:
        _workers[bot_id] = w
        _stopping.discard(bot_id)
    w.start()
    log.info("bot started polling bot_id=%s engine_pk=%s", bot_id, pk)
    return {"running": True}

def restart_if_running(bot_id: str) -> None:
    if is_running(bot_id):
        set_running(bot_id, False)
        set_running(bot_id, True)

def resume_all() -> None:
    with appdb.read() as c:
        rows = appdb.rows(c, "SELECT id FROM bots WHERE status='working'")
    for r in rows:
        try:
            set_running(r["id"], True)
        except Exception:
            log.exception("resume %s", r["id"])

def engine_pk(bot_id: str, db) -> Optional[int]:
    try:
        eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
        return int(eb.id) if eb else None
    except Exception:
        return None

def drop_engine_bot(bot_id: str) -> None:
    db = SessionLocal()
    try:
        eb = db.query(em.Bot).filter_by(public_id=bot_id).first()
        if not eb:
            return
        for c in db.query(em.Command).filter_by(bot_id=eb.id).all():
            db.delete(c)
        db.delete(eb)
        db.commit()
    except Exception:
        log.exception("drop_engine_bot")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

def uptime_text(started_iso: str) -> str:
    if not started_iso:
        return ""
    try:
        from datetime import datetime, timezone
        s = str(started_iso).replace("Z", "")
        start = datetime.fromisoformat(s.split("+")[0])
        if start.tzinfo:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        sec = max(0, int((datetime.utcnow() - start).total_seconds()))
    except Exception:
        return ""
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    if sec < 86400:
        return f"{sec // 3600}h {(sec % 3600) // 60}m"
    return f"{sec // 86400}d {(sec % 86400) // 3600}h"

def maintenance_get(bot_id: str) -> dict:
    with appdb.read() as c:
        r = appdb.one(c, "SELECT settings_json FROM settings WHERE user_id=?", (f"maint:{bot_id}",))
    data = appdb.jload(r["settings_json"], {}) if r else {}
    return {
        "enabled": bool(data.get("enabled")),
        "message": data.get("message") or "",
        "allowAdmins": bool(data.get("allowAdmins", True)),
    }
